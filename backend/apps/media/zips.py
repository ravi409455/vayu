"""ZIP of a booking's media: built once in the background, cached 7 days, opened through a
signed link that shows 'Preparing...' until it is ready."""
import os
import tempfile
import zipfile

from celery import shared_task
from django.conf import settings
from django.core import signing
from django.utils import timezone

from . import storage
from .models import MediaAsset, MediaZip

SALT = "media-zip"
KIND_TYPES = {"image": ("photo", "signature", "file"), "video": ("video",)}


def token_for(zip_id) -> str:
    return signing.TimestampSigner(salt=SALT).sign(str(zip_id))


def zip_from_token(token: str) -> MediaZip | None:
    try:
        zip_id = signing.TimestampSigner(salt=SALT).unsign(
            token, max_age=settings.ZIP_LINK_DAYS * 86400)
    except signing.BadSignature:
        return None
    return MediaZip.objects.filter(pk=zip_id).first()


def fresh(z: MediaZip) -> bool:
    return (timezone.now() - z.created_at).days < settings.ZIP_LINK_DAYS


def request_zip(booking, kind: str, excluded: list[str] | None = None) -> MediaZip:
    """The cached ZIP if there is a fresh one with the same left-out fields, else start building.
    Fields the requester may not see never go into their ZIP."""
    excluded = sorted(excluded or [])
    z = MediaZip.objects.filter(booking=booking, kind=kind,
                                excluded=excluded).order_by("-created_at").first()
    if z is not None and z.status != "failed" and fresh(z):
        return z
    z = MediaZip.objects.create(booking=booking, kind=kind, excluded=excluded)
    build_zip.delay(str(z.id))
    z.refresh_from_db()
    return z


@shared_task
def build_zip(zip_id: str) -> None:
    z = MediaZip.objects.select_related("booking").get(pk=zip_id)
    assets = list(MediaAsset.objects.filter(booking=z.booking, status="verified",
                                            kind__in=KIND_TYPES[z.kind])
                  .exclude(field_key__in=z.excluded).order_by("created_at"))
    if not assets:
        z.status = "failed"
        z.save()
        return
    counters: dict[str, int] = {}
    fd, path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    try:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as archive:
            for n, a in enumerate(assets, start=1):
                counters[a.field_key] = counters.get(a.field_key, 0) + 1
                ext = {"image/jpeg": "jpg", "image/png": "png", "application/pdf": "pdf",
                       "video/mp4": "mp4", "video/quicktime": "mov"}.get(a.content_type, "bin")
                with archive.open(f"{a.field_key}-{counters[a.field_key]}.{ext}", "w") as out:
                    for chunk in storage.stream(a.key):
                        out.write(chunk)
                z.progress = int(100 * n / len(assets))
                z.save(update_fields=["progress"])
        z.key = f"zips/{z.id}.zip"
        storage.upload_file(path, z.key, "application/zip")
        z.status, z.built_at, z.progress = "ready", timezone.now(), 100
        z.save()
    finally:
        os.unlink(path)
