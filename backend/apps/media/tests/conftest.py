import hashlib
import io
import uuid

import pytest
from moto import mock_aws
from PIL import Image

from apps.bookings.tests.conftest import booking, create, env  # noqa: F401
from apps.media import storage


@pytest.fixture(autouse=True)
def s3(settings):
    with mock_aws():
        storage.client().create_bucket(Bucket=settings.S3_BUCKET)
        yield


def jpeg(w=800, h=600, color=(200, 30, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "JPEG", quality=92)
    return buf.getvalue()


def png(w=40, h=20) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (0, 0, 0)).save(buf, "PNG")
    return buf.getvalue()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def initiate_body(booking_id, data: bytes, field_key="photo_a", kind="photo",
                  content_type="image/jpeg", **extra):
    return {"booking": booking_id, "client_uuid": str(uuid.uuid4()), "field_key": field_key,
            "kind": kind, "content_type": content_type, "size": len(data), "sha256": sha(data),
            "source": "camera", **extra}


def put_parts(initiated: dict, data: bytes, settings, only=None):
    """What the phone does with the pre-signed URLs: PUT each part straight to storage."""
    asset_id = initiated["id"]
    from apps.media.models import MediaAsset

    asset = MediaAsset.objects.get(pk=asset_id)
    size, parts = settings.MEDIA_PART_SIZE, []
    for p in initiated["parts"]:
        n = p["part_number"]
        if only is not None and n not in only:
            continue
        chunk = data[(n - 1) * size: n * size]
        r = storage.client().upload_part(Bucket=settings.S3_BUCKET, Key=asset.key,
                                         UploadId=asset.upload_id, PartNumber=n, Body=chunk)
        parts.append({"part_number": n, "etag": r["ETag"]})
    return parts


def upload(client, booking_id, data, settings, **kw):
    """Whole happy path; returns the complete response."""
    r = client.post("/api/v1/media/initiate", initiate_body(booking_id, data, **kw), format="json")
    assert r.status_code in (200, 201), r.json()
    init = r.json()
    parts = put_parts(init, data, settings)
    return client.post(f"/api/v1/media/{init['id']}/complete", {"parts": parts}, format="json")
