import hashlib
import io

from celery import shared_task
from django.utils import timezone
from PIL import Image, ImageOps

from . import storage
from .models import MediaAsset

MAX_EDGE = 2048
PREVIEW_EDGE = 480


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
    from .services import check_completion

    asset = MediaAsset.objects.get(pk=asset_id)
    if asset.status == "verified":
        return "verified"
    digest, total = hashlib.sha256(), 0
    for chunk in storage.stream(asset.key):
        digest.update(chunk)
        total += len(chunk)
    if digest.hexdigest() != asset.sha256 or total != asset.size:
        storage.delete(asset.key)
        asset.status = "failed"
        asset.save()
        return "failed"
    if asset.kind in ("photo", "signature") and asset.content_type != "image/heic":
        try:
            image = Image.open(io.BytesIO(storage.read(asset.key)))
            if max(image.size) > MAX_EDGE:  # keep the stored copy at most 2048 px on the long edge
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
    check_completion(asset.booking_id)
    return "verified"
