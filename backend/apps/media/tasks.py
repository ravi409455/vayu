import hashlib
import io
import logging

from celery import shared_task
from django.utils import timezone
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

from apps.core import log

from . import storage
from .models import MediaAsset

register_heif_opener()       # Pillow opens iPhone HEIC photos
MAX_EDGE = 2048
PREVIEW_EDGE = 480
# the first box of an MP4 / MOV file (QuickTime files may begin with any of these)
VIDEO_BOXES = {b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip"}


def _shrink(image: Image.Image, edge: int) -> Image.Image:
    image = ImageOps.exif_transpose(image)
    image.thumbnail((edge, edge))
    return image


def _jpeg(image: Image.Image, quality: int) -> bytes:
    buf = io.BytesIO()
    image.convert("RGB").save(buf, "JPEG", quality=quality)
    return buf.getvalue()


@shared_task
def verify_asset(asset_id: str) -> str:
    """Check the stored file against the phone's SHA-256, then make previews. Streams the file,
    so a 300 MB video never sits in memory. Safe to run twice (F-107): one run claims the file;
    the original is never rewritten (a picture too big or in HEIC gets a separate JPEG copy)."""
    from .services import check_completion, expected_media, report_out_of_date

    claimed = MediaAsset.objects.filter(pk=asset_id, status="uploaded").update(
        status="verifying")
    asset = MediaAsset.objects.filter(pk=asset_id).first()
    if asset is None:                     # its booking was deleted
        return "gone"
    if not claimed:                       # already done, or another run is at it
        return asset.status
    try:
        ok = _check(asset)
    except Exception:
        MediaAsset.objects.filter(pk=asset_id).update(status="uploaded")   # can be run again
        raise
    if not MediaAsset.objects.filter(pk=asset_id).exists():
        # the booking was deleted while this ran: its delete_files did not see what we wrote
        from .services import asset_keys

        for key in asset_keys(asset):
            storage.delete(key)
        return "gone"
    if not ok:
        storage.delete(asset.key)
        asset.status, asset.failed_attempts = "failed", asset.failed_attempts + 1
        asset.save(update_fields=["status", "failed_attempts"])
        return "failed"
    asset.status, asset.verified_at = "verified", timezone.now()
    asset.save(update_fields=["status", "verified_at", "preview_key", "jpeg_key"])
    log.event("upload.verified", booking=str(asset.booking_id), media=str(asset.id),
              kind=asset.kind, size=asset.size)
    booking = asset.booking
    if booking.stage == "completed" and asset.replaced_at is None:   # Ops added it afterwards
        insp = booking.counted_inspection()
        if insp is not None and str(asset.id) in expected_media(insp):
            report_out_of_date(booking.id)
    check_completion(asset.booking_id)
    return "verified"


def _check(asset: MediaAsset) -> bool:
    """Is the stored file what the phone sent (and a real picture or video)? Makes the preview
    and, when needed, the JPEG copy on the way."""
    digest, total, head = hashlib.sha256(), 0, b""
    for chunk in storage.stream(asset.key):
        digest.update(chunk)
        total += len(chunk)
        head = (head + chunk[:8])[:8]
    # a video must really be one: its first box names an MP4 / MOV container (F-244)
    not_video = asset.kind == "video" and head[4:8] not in VIDEO_BOXES
    if digest.hexdigest() != asset.sha256 or total != asset.size or not_video:
        _failed(asset, "not_a_video" if not_video else "checksum")
        return False
    # a file that is a picture gets a preview too, but its original is kept as sent (a document)
    picture_file = asset.kind == "file" and asset.content_type in ("image/jpeg", "image/png")
    if asset.kind not in ("photo", "signature") and not picture_file:
        return True
    try:
        image = Image.open(io.BytesIO(storage.read(asset.key)))
        # previews and the PDF use a JPEG of at most 2048 px: HEIC (iPhones) can't be shown
        # everywhere, and a huge photo is slow to print (F-110)
        if not picture_file and (image.format == "HEIF" or max(image.size) > MAX_EDGE):
            asset.jpeg_key = f"copies/{asset.id}.jpg"
            storage.put(asset.jpeg_key, _jpeg(_shrink(image, MAX_EDGE), 85), "image/jpeg")
        asset.preview_key = f"previews/{asset.id}.jpg"
        storage.put(asset.preview_key, _jpeg(_shrink(image, PREVIEW_EDGE), 75), "image/jpeg")
    except (OSError, ValueError, Image.DecompressionBombError):   # not a readable image
        _failed(asset, "unreadable_image")
        return False
    return True


def _failed(asset: MediaAsset, reason: str) -> None:
    """Why a file failed, findable by booking in the logs (F-212)."""
    log.event("upload.failed", level=logging.WARNING, booking=str(asset.booking_id),
              media=str(asset.id), field=asset.field_key, reason=reason)


@shared_task
def flag_stuck_uploads() -> int:
    """Every hour: one alert.stuck_upload (bell, push, webhook) per booking with files newly
    stuck past STUCK_UPLOAD_HOURS (H-09). Each file is told about once; the bell repeats a
    booking's alert at most once a day (notify.handlers.QUIET_FOR)."""
    from apps.core import events

    from .services import stuck_uploads

    fresh = list(stuck_uploads().filter(stuck_alerted=False).order_by("created_at"))
    for booking_id in dict.fromkeys(a.booking_id for a in fresh):
        first = next(a for a in fresh if a.booking_id == booking_id)
        events.emit("alert.stuck_upload", booking=str(booking_id), media=str(first.id),
                    field_key=first.field_key)
    MediaAsset.objects.filter(pk__in=[a.pk for a in fresh]).update(stuck_alerted=True)
    return len({a.booking_id for a in fresh})


@shared_task
def delete_files(keys: list[str]) -> int:
    """Objects of rows already deleted (a booking, a file): removed from storage."""
    for key in keys:
        storage.delete(key)
    return len(keys)


# which retention setting each kind follows: documents and signatures go with the photos (R-18)
RETENTION = {"photo": "photo_days", "file": "photo_days", "signature": "photo_days",
             "video": "video_days"}


@shared_task
def purge_expired(batch: int = 500) -> int:
    """Admin's retention setting: original files of completed jobs (and of cancelled jobs, counted
    from the cancel date) are deleted for good once older than the days set (0 keeps them).
    Their previews and copies and any ZIP holding them go too; so do ZIPs past their 7 days. The
    asset row stays, marked purged, so reports and links can say the files were removed. Runs
    every hour, a batch at a time."""
    import logging
    from datetime import timedelta

    from django.conf import settings
    from django.db.models import Q

    from apps.core import app_settings

    from .models import MediaZip
    from .services import asset_keys

    days = app_settings.get("media")
    done, bookings = 0, set()
    for kind, setting in RETENTION.items():
        keep = days[setting]
        if not keep:
            continue
        cutoff = timezone.now() - timedelta(days=keep)
        old = MediaAsset.objects.filter(kind=kind).filter(
            Q(booking__stage="completed", created_at__lt=cutoff)
            | Q(booking__stage="cancelled", booking__cancelled_at__lt=cutoff)) \
            .exclude(status="purged").order_by("created_at")[:batch]
        for a in old:
            for key in asset_keys(a):
                storage.delete(key)
            a.status = "purged"
            a.save(update_fields=["status"])
            bookings.add(a.booking_id)
            done += 1
    stale = timezone.now() - timedelta(days=settings.ZIP_LINK_DAYS)
    for z in MediaZip.objects.filter(Q(booking_id__in=bookings) | Q(created_at__lt=stale)):
        if z.key:                       # made before the purge, or past its 7 days (F-081)
            storage.delete(z.key)
        z.delete()
    if done:
        logging.getLogger(__name__).info("purged old media", extra={"files": done})
    return done
