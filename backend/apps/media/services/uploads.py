"""Upload protocol: initiate -> (client PUTs parts straight to storage) -> complete -> verify."""
import math
import uuid
from datetime import timedelta
from typing import Any

from botocore.exceptions import ClientError
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.permissions import scope_for
from apps.bookings.models import Booking
from apps.core.errors import fail

from .. import storage
from ..models import KINDS, MediaAsset
from .access import field_for, hidden_fields, is_manager, word, writable_booking
from .answers import max_count, submitted_answer, unarrived
from .ops import FILE_TYPES, LOOSE_LIMIT, check_ops_upload

MB = 1024 * 1024


LIMITS = {
    "photo": (25 * MB, {"image/jpeg", "image/png", "image/webp", "image/heic"}),
    "video": (300 * MB, {"video/mp4", "video/quicktime"}),
    "file": (20 * MB, {"image/jpeg", "image/png", "application/pdf"}),
    "signature": (2 * MB, {"image/png"}),
}


def booking_media(request: Any, booking_id: Any) -> list[dict[str, Any]]:
    """The files this person put on the booking (media managers: every file), oldest first, so a
    phone that lost its draft can pick them up again. Fields they may not see are left out."""
    booking = writable_booking(request, booking_id, moved_ok=True)    # experts: their own only
    qs = MediaAsset.objects.filter(booking=booking, replaced_at__isnull=True) \
        .select_related("uploaded_by").order_by("created_at")
    if scope_for(request.user, "media.manage", request) is None:
        qs = qs.filter(uploaded_by=request.user)
    hidden = hidden_fields(request.user, booking)
    return [{"id": str(a.id), "field_key": a.field_key, "kind": a.kind, "status": a.status,
             "by_ops": a.uploaded_by.role != "expert"}
            for a in qs if a.field_key not in hidden]


def _urls(asset: MediaAsset) -> list[dict[str, Any]]:
    parts = math.ceil(asset.size / settings.MEDIA_PART_SIZE)
    return [{"part_number": n, "url": storage.presign_part(asset.key, asset.upload_id, n)}
            for n in range(1, parts + 1)]


def _body(asset: MediaAsset, with_urls: bool) -> dict[str, Any]:
    out = {"id": str(asset.id), "status": asset.status, "kind": asset.kind,
           "field_key": asset.field_key, "part_size": settings.MEDIA_PART_SIZE}
    if with_urls:
        out["parts"] = _urls(asset)
    return out


def initiate(request: Any, data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Returns (body, created). Retrying with the same client_uuid returns the same asset."""
    user = request.user
    booking = writable_booking(request, data.get("booking"), moved_ok=True)   # a new own upload
    manager = is_manager(user, request)
    # a closed booking takes files only for an expert's work that has not arrived yet (done
    # offline before it was cancelled, or before Ops moved it and the other expert finished):
    # never anything added to an inspection already submitted
    closed = booking.stage == "cancelled" or (booking.stage == "completed" and not manager)
    if closed and (manager or booking.inspections.filter(
            expert=user, status__in=("submitted", "superseded")).exists()):
        raise fail("BOOKING_CLOSED", f"A {booking.stage} {word(user)} takes no new files.", 409)
    kind, ctype = data.get("kind"), data.get("content_type")
    size, sha = data.get("size"), data.get("sha256")
    if kind not in KINDS:
        raise fail("INVALID_MEDIA", f"kind must be one of {', '.join(KINDS)}.")
    limit, types = LIMITS[kind]
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise fail("INVALID_MEDIA", "size must be a positive number of bytes.")
    if size > limit:
        raise fail("TOO_LARGE", f"A {kind} may be at most {limit // MB} MB.")
    if ctype not in types:
        raise fail("INVALID_CONTENT_TYPE", f"{ctype} is not allowed for a {kind}.")
    if not isinstance(sha, str) or len(sha) != 64:
        raise fail("INVALID_MEDIA", "sha256 must be the file's 64-character hex digest.")
    source = data.get("source", "camera")
    if source not in ("camera", "gallery"):
        raise fail("INVALID_MEDIA", "source must be camera or gallery.")
    try:
        client_uuid = uuid.UUID(str(data.get("client_uuid")))
    except ValueError as e:
        raise fail("INVALID_MEDIA", "client_uuid must be a UUID.") from e
    existing = MediaAsset.objects.filter(client_uuid=client_uuid).first()
    if existing is not None:
        if existing.booking_id != booking.id or existing.uploaded_by_id != user.pk:
            raise fail("UUID_CONFLICT", "That request ID belongs to another request.", 409)
        if existing.status == "failed":   # failed checksum: start the upload again
            existing.status, existing.upload_id = "pending", storage.create_multipart(
                existing.key, existing.content_type)
            existing.sha256, existing.size = sha, size
            existing.save()
        return _body(existing, existing.status == "pending"), False
    field = field_for(booking, data.get("field_key", ""))
    if field.type != kind:
        raise fail("WRONG_KIND", f"'{field.key}' takes {field.type}, not {kind}.")
    if kind == "file" and ctype not in set().union(
            *(FILE_TYPES[a] for a in field.config.get("allowed", ["image", "pdf"]))):
        raise fail("INVALID_CONTENT_TYPE", f"'{field.label}' does not take {ctype}.")
    replaces = data.get("replaces")
    if manager:      # Ops: the limit is what the submitted answers hold (checked again on attach)
        check_ops_upload(booking, field, user)
        _, _, ids = submitted_answer(booking, field)
        if replaces is not None and str(replaces) not in ids:
            raise fail("UNKNOWN_MEDIA", "The file to replace is not on this field.")
        # places held by files that never arrived can be taken over, one upload each
        if replaces is None and len(ids) - len(unarrived(booking, ids)) >= max_count(field):
            raise fail("TOO_MANY", f"'{field.label}' takes at most {max_count(field)}. "
                       "Replace one instead.", 409)
        # uploads not (yet) in the answers: a few may be left by closed tabs, never a pile
        loose = MediaAsset.objects.filter(booking=booking, field_key=field.key, uploaded_by=user,
                                          replaced_at__isnull=True).exclude(pk__in=ids) \
            .exclude(status="failed").count()
        if loose >= LOOSE_LIMIT:
            raise fail("TOO_MANY", "Too many uploads on this field are not saved yet. Wait for "
                       "them to finish, or reload the page.", 409)
    elif replaces is not None:
        raise fail("UNKNOWN_MEDIA", "Only Ops replace a file.")
    with transaction.atomic():
        Booking.objects.select_for_update().get(pk=booking.pk)   # two uploads must not both fit
        # an expert's limit counts their own uploads: two experts on one job (a conflict for Ops)
        # never use up each other's places
        # a failed upload holds no place (the retake replaces it), nor one left unfinished past
        # the stuck limit (a closed tab, cleared storage: no device resumes it any more)
        stale = timezone.now() - timedelta(hours=settings.STUCK_UPLOAD_HOURS)
        if not manager and MediaAsset.objects.filter(
                booking=booking, field_key=field.key, uploaded_by=user).exclude(
                status="failed").exclude(status="pending", created_at__lt=stale).count() \
                >= max_count(field):
            raise fail("TOO_MANY", f"'{field.key}' takes at most {max_count(field)}.", 409)
        asset = MediaAsset(client_uuid=client_uuid, booking=booking, uploaded_by=user,
                           field_key=field.key, kind=kind, content_type=ctype, size=size,
                           sha256=sha, source=source)
        asset.key = f"bookings/{booking.id}/{asset.id}"
        asset.upload_id = storage.create_multipart(asset.key, ctype)
        asset.save()
    return _body(asset, True), True




def progress(asset: MediaAsset) -> dict[str, Any]:
    body = _body(asset, False)
    body["uploaded_parts"] = (storage.list_parts(asset.key, asset.upload_id)
                              if asset.upload_id else [])
    return body


def complete(asset: MediaAsset, parts: list[dict[str, Any]]) -> MediaAsset:
    from ..tasks import verify_asset

    if asset.status in ("uploaded", "verifying", "verified"):
        return asset
    if not asset.upload_id:
        raise fail("NOT_UPLOADING", "Start the upload again.", 409)
    have = {p["part_number"]: p["etag"] for p in storage.list_parts(asset.key, asset.upload_id)}
    wanted = range(1, math.ceil(asset.size / settings.MEDIA_PART_SIZE) + 1)
    missing = [n for n in wanted if n not in have]
    if missing or {p["part_number"]: p["etag"] for p in parts} != have:
        raise fail("INCOMPLETE_UPLOAD", "Some parts are missing or do not match.", missing=missing)
    try:
        storage.complete_multipart(asset.key, asset.upload_id, parts)
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") != "NoSuchUpload":
            raise
        asset.refresh_from_db()          # a parallel request finished it first
        if asset.status in ("uploaded", "verifying", "verified"):
            return asset
        raise fail("NOT_UPLOADING", "Start the upload again.", 409) from e
    asset.upload_id, asset.status = "", "uploaded"
    asset.save()
    # checked in the background (F-162): the phone and web read "verified" or "failed" from
    # GET media/<id> and send the file again when it failed
    verify_asset.delay(str(asset.id))
    asset.refresh_from_db()
    return asset


def stuck_uploads(hours: int | None = None) -> Any:
    """Files still not arrived after the limit that someone waits for: not on a finished or
    cancelled job, not failed (the phone sends a new one) and not replaced by Ops (F-149)."""
    cutoff = timezone.now() - timedelta(hours=hours or settings.STUCK_UPLOAD_HOURS)
    return MediaAsset.objects.exclude(status__in=("verified", "purged", "failed")) \
        .filter(created_at__lt=cutoff, replaced_at__isnull=True) \
        .exclude(booking__stage__in=("completed", "cancelled"))
