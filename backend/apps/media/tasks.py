import hashlib
import io

from celery import shared_task
from django.utils import timezone
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

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
    asset = MediaAsset.objects.get(pk=asset_id)
    if not claimed:                       # already done, or another run is at it
        return asset.status
    try:
        ok = _check(asset)
    except Exception:
        MediaAsset.objects.filter(pk=asset_id).update(status="uploaded")   # can be run again
        raise
    if not ok:
        storage.delete(asset.key)
        asset.status = "failed"
        asset.save(update_fields=["status"])
        return "failed"
    asset.status, asset.verified_at = "verified", timezone.now()
    asset.save(update_fields=["status", "verified_at", "preview_key", "jpeg_key"])
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
        return False
    return True


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
def purge_expired(batch: int = 500) -> int:
    """Admin's retention setting: original photos and videos of completed jobs are deleted for
    good once they are older than the days set (0 keeps them). Their previews, print copies and
    any ZIP holding them go too. The asset row stays, marked purged, so reports and links can
    say the files were removed. Runs every hour, a batch at a time."""
    import logging
    from datetime import timedelta

    from apps.core import app_settings
    from apps.reports.render import print_keys

    from .models import MediaZip

    days = app_settings.get("media")
    done, bookings = 0, set()
    for kind in ("photo", "video"):
        keep = days[f"{kind}_days"]
        if not keep:
            continue
        old = MediaAsset.objects.filter(kind=kind, booking__stage="completed",
                                        created_at__lt=timezone.now() - timedelta(days=keep)) \
            .exclude(status="purged").order_by("created_at")[:batch]
        for a in old:
            for key in filter(None, (a.key, a.preview_key, a.jpeg_key, *print_keys(a.id))):
                storage.delete(key)
            a.status = "purged"
            a.save(update_fields=["status"])
            bookings.add(a.booking_id)
            done += 1
    for z in MediaZip.objects.filter(booking_id__in=bookings):      # ZIPs made before
        if z.key:
            storage.delete(z.key)
        z.delete()
    if done:
        logging.getLogger(__name__).info("purged old media", extra={"files": done})
    return done
