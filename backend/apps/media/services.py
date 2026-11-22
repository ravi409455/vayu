"""Upload protocol: initiate -> (client PUTs parts straight to storage) -> complete -> verify."""
import math
import uuid
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.accounts.permissions import scope_for
from apps.bookings.models import Booking, Inspection
from apps.bookings.services import err
from apps.bookings.submissions import inspection_version, ops_version, own_filter
from apps.core import events
from apps.forms.fieldtypes import DEFAULT_MAX_COUNT
from apps.forms.models import Field

from . import storage
from .models import KINDS, MediaAsset, MediaZip

MB = 1024 * 1024
LIMITS = {
    "photo": (25 * MB, {"image/jpeg", "image/png", "image/webp", "image/heic"}),
    "video": (300 * MB, {"video/mp4", "video/quicktime"}),
    "file": (20 * MB, {"image/jpeg", "image/png", "application/pdf"}),
    "signature": (2 * MB, {"image/png"}),
}


def writable_booking(request, booking_id) -> Booking:
    """The booking if this user may add media to it: its expert (own scope) or media managers."""
    user = request.user
    qs = Booking.objects.all()
    if scope_for(user, "media.manage", request) is None \
            and scope_for(user, "submissions.fill", request) == "own":
        qs = qs.filter(own_filter(user)).distinct()
    b = qs.filter(pk=booking_id).first()
    if b is None:
        raise err("NOT_FOUND", "Booking not found.", 404)
    return b


def readable_booking(request, booking_id) -> Booking:
    qs = Booking.objects.all()
    if scope_for(request.user, "submissions.view", request) == "own":
        qs = qs.filter(own_filter(request.user)).distinct()
    b = qs.filter(pk=booking_id).first()
    if b is None:
        raise err("NOT_FOUND", "Booking not found.", 404)
    return b


def field_for(booking: Booking, field_key: str) -> Field:
    """The form field (inspection or ops form) a media upload belongs to."""
    versions = []
    insp = booking.inspections.order_by("-created_at").first()
    versions.append(insp.form_version if insp else inspection_version(booking.inspection_type))
    if (ov := ops_version()) is not None:
        versions.append(ov)
    for v in versions:
        f = Field.objects.filter(version=v, key=field_key).first()
        if f is not None:
            return f
    raise err("UNKNOWN_FIELD", f"'{field_key}' is not a field of this inspection.")


def _urls(asset: MediaAsset) -> list[dict]:
    parts = math.ceil(asset.size / settings.MEDIA_PART_SIZE)
    return [{"part_number": n, "url": storage.presign_part(asset.key, asset.upload_id, n)}
            for n in range(1, parts + 1)]


def _body(asset: MediaAsset, with_urls: bool) -> dict:
    out = {"id": str(asset.id), "status": asset.status, "kind": asset.kind,
           "field_key": asset.field_key, "part_size": settings.MEDIA_PART_SIZE}
    if with_urls:
        out["parts"] = _urls(asset)
    return out


def initiate(request, data: dict) -> tuple[dict, bool]:
    """Returns (body, created). Retrying with the same client_uuid returns the same asset."""
    user = request.user
    booking = writable_booking(request, data.get("booking"))
    kind, ctype = data.get("kind"), data.get("content_type")
    size, sha = data.get("size"), data.get("sha256")
    if kind not in KINDS:
        raise err("INVALID_MEDIA", f"kind must be one of {', '.join(KINDS)}.")
    limit, types = LIMITS[kind]
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise err("INVALID_MEDIA", "size must be a positive number of bytes.")
    if size > limit:
        raise err("TOO_LARGE", f"A {kind} may be at most {limit // MB} MB.")
    if ctype not in types:
        raise err("INVALID_CONTENT_TYPE", f"{ctype} is not allowed for a {kind}.")
    if not isinstance(sha, str) or len(sha) != 64:
        raise err("INVALID_MEDIA", "sha256 must be the file's 64-character hex digest.")
    source = data.get("source", "camera")
    if source not in ("camera", "gallery"):
        raise err("INVALID_MEDIA", "source must be camera or gallery.")
    try:
        client_uuid = uuid.UUID(str(data.get("client_uuid")))
    except ValueError as e:
        raise err("INVALID_MEDIA", "client_uuid must be a UUID.") from e
    existing = MediaAsset.objects.filter(client_uuid=client_uuid).first()
    if existing is not None:
        if existing.booking_id != booking.id or existing.uploaded_by_id != user.pk:
            raise err("UUID_CONFLICT", "That request ID belongs to another request.", 409)
        if existing.status == "failed":   # failed checksum: start the upload again
            existing.status, existing.upload_id = "pending", storage.create_multipart(
                existing.key, existing.content_type)
            existing.sha256, existing.size = sha, size
            existing.save()
        return _body(existing, existing.status == "pending"), False
    field = field_for(booking, data.get("field_key", ""))
    if field.type != kind:
        raise err("WRONG_KIND", f"'{field.key}' takes {field.type}, not {kind}.")
    limit_count = field.config.get("max_count", DEFAULT_MAX_COUNT.get(kind, 1))
    if kind == "signature":
        limit_count = 1
    if MediaAsset.objects.filter(booking=booking, field_key=field.key).count() >= limit_count:
        raise err("TOO_MANY", f"'{field.key}' takes at most {limit_count}.", 409)
    asset = MediaAsset(client_uuid=client_uuid, booking=booking, uploaded_by=user,
                       field_key=field.key, kind=kind, content_type=ctype, size=size, sha256=sha,
                       source=source)
    asset.key = f"bookings/{booking.id}/{asset.id}"
    asset.upload_id = storage.create_multipart(asset.key, ctype)
    asset.save()
    return _body(asset, True), True


def progress(asset: MediaAsset) -> dict:
    body = _body(asset, False)
    body["uploaded_parts"] = (storage.list_parts(asset.key, asset.upload_id)
                              if asset.upload_id else [])
    return body


def complete(asset: MediaAsset, parts: list[dict]) -> MediaAsset:
    from .tasks import verify_asset

    if asset.status in ("uploaded", "verified"):
        return asset
    if not asset.upload_id:
        raise err("NOT_UPLOADING", "Start the upload again.", 409)
    have = {p["part_number"]: p["etag"] for p in storage.list_parts(asset.key, asset.upload_id)}
    wanted = range(1, math.ceil(asset.size / settings.MEDIA_PART_SIZE) + 1)
    missing = [n for n in wanted if n not in have]
    if missing or {p["part_number"]: p["etag"] for p in parts} != have:
        raise err("INCOMPLETE_UPLOAD", "Some parts are missing or do not match.", missing=missing)
    storage.complete_multipart(asset.key, asset.upload_id, parts)
    asset.upload_id, asset.status = "", "uploaded"
    asset.save()
    verify_asset.delay(str(asset.id))
    asset.refresh_from_db()
    if asset.status == "failed":
        raise err("CHECKSUM_MISMATCH", "The upload was corrupted; upload it again.", 409)
    return asset


def referenced_ids(version, answers: dict) -> dict[str, str]:
    """{media id: field type} for every media reference in one form's cleaned answers."""
    out: dict[str, str] = {}
    for f in Field.objects.filter(version=version, type__in=KINDS):
        value = answers.get(f.key)
        for mid in ([value] if isinstance(value, str) else value or []):
            out[str(mid)] = f.type
    return out


def reference_errors(booking: Booking, parts: list[tuple]) -> dict[str, str]:
    """Answers may only point at this booking's media of the right kind."""
    errors: dict[str, str] = {}
    for version, answers in parts:
        if version is None:
            continue
        refs = referenced_ids(version, answers)
        found = {str(a.id): a for a in MediaAsset.objects.filter(booking=booking,
                                                                  id__in=list(refs))}
        for f in Field.objects.filter(version=version, type__in=KINDS):
            value = answers.get(f.key)
            for mid in ([value] if isinstance(value, str) else value or []):
                asset = found.get(str(mid))
                if asset is None:
                    errors[f.key] = "UNKNOWN_MEDIA"
                elif asset.kind != f.type or asset.field_key != f.key:
                    errors[f.key] = "WRONG_MEDIA_KIND"
    return errors


def expected_media(inspection: Inspection) -> set[str]:
    ops = ops_version()
    ids = set(referenced_ids(inspection.form_version, inspection.answers.get("inspection") or {}))
    if ops is not None:
        ids |= set(referenced_ids(ops, inspection.answers.get("ops") or {}))
    return ids


def check_completion(booking_id) -> bool:
    """Submitted -> Completed once every referenced file is verified. Exactly once."""
    from django.db import transaction

    with transaction.atomic():
        b = Booking.objects.select_for_update().get(pk=booking_id)
        if b.stage != "submitted":
            return False
        insp = b.inspections.filter(status="submitted").order_by("-submitted_at").first()
        if insp is None:
            return False
        ids = expected_media(insp)
        verified = set(map(str, MediaAsset.objects.filter(
            booking=b, id__in=list(ids), status="verified").values_list("id", flat=True)))
        if verified != ids:
            return False
        b.stage = "completed"
        b.row_version += 1
        b.last_change = {"by": "system", "at": timezone.now().isoformat(), "keys": ["stage"]}
        b.save()
    events.emit("inspection.completed", booking=str(b.id), booking_id=b.booking_id,
                inspection=str(insp.id))
    events.emit("media.completed", booking=str(b.id), booking_id=b.booking_id)
    return True


def delete_asset(actor, asset: MediaAsset) -> None:
    """Ops remove a file after submission: the object, its preview, its reference in the answers."""
    from django.db import transaction

    from apps.scoring import service as scoring

    with transaction.atomic():
        for insp in asset.booking.inspections.select_for_update().all():
            changed = False
            for part in ("inspection", "ops"):
                answers = dict(insp.answers.get(part) or {})
                for key, value in answers.items():
                    if value == str(asset.id):
                        answers[key] = None
                        changed = True
                    elif isinstance(value, list) and str(asset.id) in value:
                        answers[key] = [v for v in value if v != str(asset.id)]
                        changed = True
                if changed:
                    insp.answers = {**insp.answers, part: {k: v for k, v in answers.items()
                                                           if v not in (None, [])}}
            if changed:
                insp.row_version += 1
                insp.last_edited_by, insp.last_edited_at = actor, timezone.now()
                insp.last_change = {"by": actor.username, "at": insp.last_edited_at.isoformat(),
                                    "keys": [asset.field_key]}
                insp.save()
                scoring.recompute(insp)
        MediaZip.objects.filter(booking=asset.booking).delete()   # cached ZIPs no longer match
        for key in (asset.key, asset.preview_key):
            if key:
                storage.delete(key)
        if asset.upload_id:
            storage.abort_multipart(asset.key, asset.upload_id)
        asset.delete()
    events.emit("media.deleted", booking=str(asset.booking_id), field_key=asset.field_key)


def stuck_uploads(hours: int | None = None):
    cutoff = timezone.now() - timedelta(hours=hours or settings.STUCK_UPLOAD_HOURS)
    return MediaAsset.objects.exclude(status="verified").filter(created_at__lt=cutoff)
