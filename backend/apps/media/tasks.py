import hashlib
import io

from celery import shared_task
from django.utils import timezone
from PIL import Image, ImageOps

from . import storage
from .models import MediaAsset

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
    so a 300 MB video never sits in memory."""
    from .services import check_completion, expected_media, rebuild_report

    asset = MediaAsset.objects.get(pk=asset_id)
    if asset.status == "verified":
        return "verified"
    digest, total, head = hashlib.sha256(), 0, b""
    for chunk in storage.stream(asset.key):
        digest.update(chunk)
        total += len(chunk)
        head = (head + chunk[:8])[:8]
    # a video must really be one: its first box names an MP4 / MOV container (F-244)
    not_video = asset.kind == "video" and head[4:8] not in VIDEO_BOXES
    if digest.hexdigest() != asset.sha256 or total != asset.size or not_video:
        storage.delete(asset.key)
        asset.status = "failed"
        asset.save()
        return "failed"
    # a file that is a picture gets a preview too, but its original is kept as sent (a document)
    picture_file = asset.kind == "file" and asset.content_type in ("image/jpeg", "image/png")
    picture = asset.kind in ("photo", "signature") and asset.content_type != "image/heic"
    if picture or picture_file:
        try:
            image = Image.open(io.BytesIO(storage.read(asset.key)))
            if not picture_file and max(image.size) > MAX_EDGE:  # stored copy: at most 2048 px
                storage.put(asset.key, _jpeg(_shrink(image, MAX_EDGE), 85), "image/jpeg")
                asset.content_type = "image/jpeg"
            asset.preview_key = f"previews/{asset.id}.jpg"
            storage.put(asset.preview_key, _jpeg(_shrink(image, PREVIEW_EDGE), 75), "image/jpeg")
        except (OSError, ValueError, Image.DecompressionBombError):   # not a readable image
            storage.delete(asset.key)
            asset.status = "failed"
            asset.save()
            return "failed"
    asset.status, asset.verified_at = "verified", timezone.now()
    asset.save()
    booking = asset.booking
    if booking.stage == "completed" and asset.replaced_at is None:   # Ops added it afterwards
        insp = booking.inspections.filter(status="submitted").order_by("-submitted_at").first()
        if insp is not None and str(asset.id) in expected_media(insp):
            rebuild_report(booking.id)
    check_completion(asset.booking_id)
    return "verified"


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
            for key in filter(None, (a.key, a.preview_key, *print_keys(a.id))):
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
