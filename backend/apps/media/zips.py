"""ZIP of a booking's media: built once in the background, cached 7 days, opened through a
signed link that shows 'Preparing...' until it is ready."""
import os
import re
import tempfile
import zipfile

from celery import shared_task
from django.conf import settings
from django.core import signing
from django.utils import timezone

from . import storage
from .models import MediaAsset, MediaZip

SALT = "media-zip"
# image: every picture and document (Ops); photo: photos only (the customer's report link)
KIND_TYPES = {"image": ("photo", "signature", "file"), "photo": ("photo",), "video": ("video",)}
TITLES = {"image": "files", "photo": "photos", "video": "videos"}
BAD_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def download_name(z: MediaZip) -> str:
    """What the browser saves it as: "DEMO-3 photos.zip"."""
    return f"{z.booking.booking_id} {TITLES.get(z.kind, z.kind)}.zip"


def _places(booking) -> dict[str, tuple[int, str, str]]:
    """field key -> (form order, section title, field label), for readable names in the ZIP."""
    from apps.bookings.submissions import current_versions
    from apps.core.errors import CodedError
    from apps.forms.models import Field

    try:
        versions = [v for v in current_versions(booking).values() if v is not None]
    except CodedError:
        return {}
    fields = Field.objects.filter(version__in=versions).select_related("section__page") \
        .order_by("version_id", "section__page__order", "section__order", "order", "id")
    out: dict[str, tuple[int, str, str]] = {}
    for n, f in enumerate(fields):
        out.setdefault(f.key, (n, f.section.title, f.label))
    return out


def _clean(text: str) -> str:
    return BAD_CHARS.sub("-", text).strip(" .-")[:80] or "file"


def entry_names(places: dict, assets: list) -> list[str]:
    """ "Exterior/Front bumper.jpg", "Exterior/Front bumper 2.jpg" in form order; a field no form
    knows keeps its key: "photo_x-1.jpg"."""
    total: dict[str, int] = {}
    for a in assets:
        total[a.field_key] = total.get(a.field_key, 0) + 1
    seen: dict[str, int] = {}
    used: set[str] = set()
    out = []
    for a in assets:
        seen[a.field_key] = seen.get(a.field_key, 0) + 1
        k = seen[a.field_key]
        ext = {"image/jpeg": "jpg", "image/png": "png", "application/pdf": "pdf",
               "video/mp4": "mp4", "video/quicktime": "mov"}.get(a.content_type, "bin")
        if a.field_key in places:
            _, section, label = places[a.field_key]
            base = f"{_clean(section)}/{_clean(label)}"
            base += f" {k}" if total[a.field_key] > 1 else ""
        else:
            base = f"{a.field_key}-{k}"
        name, n = f"{base}.{ext}", 1
        while name in used:                      # two fields with the same label
            n += 1
            name = f"{base} ({n}).{ext}"
        used.add(name)
        out.append(name)
    return out


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
                                            replaced_at__isnull=True,
                                            kind__in=KIND_TYPES[z.kind])
                  .exclude(field_key__in=z.excluded).order_by("created_at"))
    if not assets:
        z.status = "failed"
        z.save()
        return
    places = _places(z.booking)
    assets.sort(key=lambda a: (places.get(a.field_key, (10**9,))[0], a.created_at))
    names = entry_names(places, assets)
    fd, path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    try:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as archive:
            for n, (a, name) in enumerate(zip(assets, names, strict=True), start=1):
                with archive.open(name, "w") as out:
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
