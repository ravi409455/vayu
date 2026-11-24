"""Pictures uploaded in the builder for 'image' fields (e.g. a payment QR code)."""
import base64
import binascii
import hashlib
import io

from PIL import Image, UnidentifiedImageError

from apps.accounts import audit
from apps.core.errors import CodedError
from apps.media import storage

from .models import FormAsset

MAX_BYTES = 2 * 1024 * 1024
FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg"}


def _check(data: bytes) -> str:
    """The real content type of the picture, or an error. The file's own bytes decide."""
    if not data or len(data) > MAX_BYTES:
        raise CodedError("INVALID_IMAGE", "The picture must be at most 2 MB.", 400)
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
            fmt = img.format or ""
    except (UnidentifiedImageError, OSError, SyntaxError) as e:
        raise CodedError("INVALID_IMAGE", "That is not a PNG or JPEG picture.", 400) from e
    if fmt not in FORMATS:
        raise CodedError("INVALID_IMAGE", "Only PNG and JPEG pictures are accepted.", 400)
    return FORMATS[fmt]


def create_asset(actor, data: bytes, name: str = "") -> FormAsset:
    """A new picture; with a name it is in the picture library. The same picture uploaded again
    to the library is the one already there (named if it was not)."""
    content_type = _check(data)
    digest = hashlib.sha256(data).hexdigest()
    if name:
        same = FormAsset.objects.filter(sha256=digest).order_by("created_at").first()
        if same is not None:
            if not same.name:
                same.name = name
                same.save(update_fields=["name"])
            return same
    asset = FormAsset(content_type=content_type, size=len(data), created_by=actor, name=name,
                      sha256=digest)
    asset.key = f"form-assets/{asset.id}"
    storage.put(asset.key, data, content_type)
    asset.save()
    audit.record(actor, "form.asset_upload", "form_asset", asset.id, "Uploaded a form picture")
    return asset


def url(asset: FormAsset) -> str:
    return storage.presign_get(asset.key, expires=3600)


def export(asset: FormAsset) -> dict:
    return {"content_type": asset.content_type, "name": asset.name,
            "data": base64.b64encode(storage.read(asset.key)).decode()}


def import_from_bundle(actor, payload, library: bool = False) -> FormAsset:
    """library: a report template's picture, kept in the picture library (once)."""
    try:
        data = base64.b64decode(payload["data"], validate=True)
        name = str(payload.get("name") or "Imported picture")[:100] if library else ""
    except (KeyError, TypeError, AttributeError, binascii.Error) as e:
        raise CodedError("INVALID_BUNDLE", "A picture in the bundle is damaged.", 400) from e
    return create_asset(actor, data, name)
