"""Thin wrapper over the S3 API (Cloudflare R2 in production). Everything that touches the
bucket goes through here so tests can swap in an in-memory S3."""
import os
import time
from typing import Any

import boto3
from botocore.config import Config
from django.conf import settings

_made: tuple[tuple, Any] | None = None       # (what it was made for, the client)


def _forget() -> None:
    """A forked process (a Celery or gunicorn worker) makes its own: a connection is never
    shared between processes."""
    global _made
    _made = None


os.register_at_fork(after_in_child=_forget)


def client():
    """The process's one R2 client, made on first use and kept: a new one per call cost ~0.3-0.7 s
    on the cloud rehearsal (the library's setup again, and a new secure connection to R2). A
    client is safe to share between threads (gunicorn's threads, the PDF's photo fetchers)."""
    global _made
    made_for = (settings.S3_ENDPOINT_URL, settings.S3_REGION, settings.S3_ACCESS_KEY_ID,
                settings.S3_SECRET_ACCESS_KEY)
    made = _made
    if made is None or made[0] != made_for:
        # two threads may both get here at first use: each makes one (its own session, so that
        # is safe) and one is kept; no lock needed for a one-off spare
        made = _made = (made_for, _new())
    return made[1]


def _new():
    c = boto3.session.Session().client(
        "s3", endpoint_url=settings.S3_ENDPOINT_URL or None, region_name=settings.S3_REGION,
        aws_access_key_id=settings.S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
        # short timeouts (F-209): a slow R2 never holds a web worker for minutes
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                      connect_timeout=5, read_timeout=30,
                      retries={"max_attempts": 3, "mode": "standard"},
                      # kept-open connections: 4 web threads, or a PDF's 8 photo fetchers
                      max_pool_connections=16))
    if os.environ.get("R2_CALL_LOG") == "1":      # load tests: each R2 call's own time
        c.meta.events.register("before-call.s3", _started)
        c.meta.events.register("after-call.s3", _finished)
    return c


def _started(context: dict, **_: Any) -> None:
    context["r2_started"] = time.monotonic()


def _finished(context: dict, model: Any, http_response: Any, **_: Any) -> None:
    from apps.core import log

    if "r2_started" in context:
        log.event("r2.call", op=model.name, status=getattr(http_response, "status_code", 0),
                  duration_ms=round(1000 * (time.monotonic() - context["r2_started"])))


def create_multipart(key: str, content_type: str) -> str:
    return client().create_multipart_upload(Bucket=settings.S3_BUCKET, Key=key,
                                            ContentType=content_type)["UploadId"]


def presign_part(key: str, upload_id: str, part_number: int) -> str:
    return client().generate_presigned_url(
        "upload_part", ExpiresIn=settings.MEDIA_URL_TTL,
        Params={"Bucket": settings.S3_BUCKET, "Key": key, "UploadId": upload_id,
                "PartNumber": part_number})


def list_parts(key: str, upload_id: str) -> list[dict]:
    out, marker = [], 0
    while True:
        r = client().list_parts(Bucket=settings.S3_BUCKET, Key=key, UploadId=upload_id,
                                PartNumberMarker=marker)
        out += [{"part_number": p["PartNumber"], "etag": p["ETag"], "size": p["Size"]}
                for p in r.get("Parts", [])]
        if not r.get("IsTruncated"):
            return out
        marker = r["NextPartNumberMarker"]  # pragma: no cover - only past 1000 parts


def complete_multipart(key: str, upload_id: str, parts: list[dict]) -> None:
    client().complete_multipart_upload(
        Bucket=settings.S3_BUCKET, Key=key, UploadId=upload_id,
        MultipartUpload={"Parts": [{"PartNumber": p["part_number"], "ETag": p["etag"]}
                                   for p in sorted(parts, key=lambda p: p["part_number"])]})


def abort_multipart(key: str, upload_id: str) -> None:
    client().abort_multipart_upload(Bucket=settings.S3_BUCKET, Key=key, UploadId=upload_id)


def head(key: str) -> dict:
    return client().head_object(Bucket=settings.S3_BUCKET, Key=key)


def read(key: str, c=None) -> bytes:
    """c: a client to reuse (making one per call costs setup time; a report reads 150 photos)."""
    return (c or client()).get_object(Bucket=settings.S3_BUCKET, Key=key)["Body"].read()


def stream(key: str, chunk: int = 1024 * 1024):
    return client().get_object(Bucket=settings.S3_BUCKET, Key=key)["Body"].iter_chunks(chunk)


def put(key: str, data: bytes, content_type: str, c=None) -> None:
    (c or client()).put_object(Bucket=settings.S3_BUCKET, Key=key, Body=data,
                               ContentType=content_type)


def upload_file(path: str, key: str, content_type: str) -> None:
    client().upload_file(path, settings.S3_BUCKET, key, ExtraArgs={"ContentType": content_type})


def delete(key: str) -> None:
    client().delete_object(Bucket=settings.S3_BUCKET, Key=key)


def exists(key: str) -> bool:
    try:
        head(key)
        return True
    except client().exceptions.ClientError:
        return False


def link_ttl() -> int:
    """How long a file link works, in seconds."""
    return int(settings.MEDIA_URL_TTL)


def presign_get(key: str, filename: str | None = None, expires: int | None = None,
                s3=None) -> str:
    """[s3]: a client to reuse (making one costs a few ms: a booking's links make one, not two
    per file)."""
    params = {"Bucket": settings.S3_BUCKET, "Key": key}
    if filename:
        params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
    return (s3 or client()).generate_presigned_url(
        "get_object", ExpiresIn=expires or link_ttl(), Params=params)
