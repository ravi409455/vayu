"""Upload protocol: initiate -> (client PUTs parts straight to storage) -> complete -> verify."""
import json
import math
import uuid
from datetime import timedelta

from botocore.exceptions import ClientError
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.permissions import scope_for
from apps.bookings import activity
from apps.bookings.models import Booking, Inspection
from apps.bookings.services import err
from apps.bookings.submissions import current_versions, deliver_filter, own_filter
from apps.core import events
from apps.core import tasks as core_tasks
from apps.core.errors import CodedError
from apps.forms.access import hidden_inspection_forms, levels_for
from apps.forms.fieldtypes import DEFAULT_MAX_COUNT
from apps.forms.models import PARTS, Field

from . import storage
from .models import KINDS, MediaAsset, MediaZip

MB = 1024 * 1024
LIMITS = {
    "photo": (25 * MB, {"image/jpeg", "image/png", "image/webp", "image/heic"}),
    "video": (300 * MB, {"video/mp4", "video/quicktime"}),
    "file": (20 * MB, {"image/jpeg", "image/png", "application/pdf"}),
    "signature": (2 * MB, {"image/png"}),
}


def writable_booking(request, booking_id, moved_ok: bool = False) -> Booking:
    """The booking if this user may add media to it: its expert (own scope) or media managers.
    [moved_ok]: also a job moved away from them meanwhile, for their own new or own uploads only."""
    user = request.user
    qs = Booking.objects.all()
    if scope_for(user, "media.manage", request) is None \
            and scope_for(user, "submissions.fill", request) == "own":
        qs = qs.filter(deliver_filter(user) if moved_ok else own_filter(user)).distinct()
    b = qs.filter(pk=booking_id).first()
    if b is None:
        raise err("NOT_FOUND", f"{word(user).capitalize()} not found.", 404)
    return b


def word(user) -> str:
    """What this person calls a booking (docs/plan-leads-bookings-words.md): experts a lead."""
    return "lead" if getattr(user, "role", "") == "expert" else "booking"


def readable_booking(request, booking_id) -> Booking:
    qs = Booking.objects.all()
    if scope_for(request.user, "submissions.view", request) == "own":
        qs = qs.filter(own_filter(request.user)).distinct()
    b = qs.filter(pk=booking_id).first()
    if b is None:
        raise err("NOT_FOUND", f"{word(request.user).capitalize()} not found.", 404)
    return b


def field_for(booking: Booking, field_key: str) -> Field:
    """The form field (custom, start or end form) a media upload belongs to."""
    for v in current_versions(booking).values():
        f = Field.objects.filter(version=v, key=field_key).first() if v else None
        if f is not None:
            return f
    raise err("UNKNOWN_FIELD", f"'{field_key}' is not a field of this inspection.")


def hidden_fields(user, booking: Booking) -> set[str]:
    """Media field keys this user may not see at the booking's current stage (an expert's own
    form too: Ops-only photo fields stay Ops-only)."""
    if user.role == "admin":
        return set()
    try:
        pinned = current_versions(booking)
    except CodedError:       # no form says what this user may see: fail closed, hide every file
        return set(MediaAsset.objects.filter(booking=booking).values_list("field_key", flat=True))
    main, versions = pinned["inspection"], list(pinned.values())
    out: set[str] = set()
    if main.form_id in hidden_inspection_forms(user):          # the whole submission is off limits
        out |= set(Field.objects.filter(version=main, type__in=KINDS).values_list("key", flat=True))
    for v in versions:
        if v is not None:
            out |= {k for k, level in levels_for(v, user.role, booking.stage).items()
                    if level == "hidden"}
    return out


OPS_KINDS = ("photo", "video", "file")
# what a file field's "allowed" setting lets in
FILE_TYPES = {"image": {"image/jpeg", "image/png"}, "pdf": {"application/pdf"}}
OPS_STAGES = ("submitted", "completed")
LOOSE_LIMIT = 10      # Ops uploads per field not in the answers (yet)


def is_manager(user, request=None) -> bool:
    return scope_for(user, "media.manage", request) is not None


def check_ops_upload(booking: Booking, field: Field, user) -> None:
    """What Ops and Admin may put on a booking: photos, videos and files, once the expert has
    submitted, on fields the Admin has not blocked and they may see."""
    if field.key in hidden_fields(user, booking):
        raise err("UNKNOWN_FIELD", f"'{field.key}' is not a field of this inspection.")
    if user.role != "admin" and levels_for(field.version, user.role, booking.stage).get(
            field.key) != "edit":
        raise err("FIELD_ACCESS", f"You cannot change '{field.label}' at this stage.", 403)
    if field.type not in OPS_KINDS:
        raise err("OPS_UPLOAD_NOT_ALLOWED", "Ops can add only photos, videos and files.", 403)
    if booking.stage not in OPS_STAGES:
        raise err("NOT_SUBMITTED", "Files can be added only after the expert submits.", 409)
    if field.config.get("ops_upload", True) is not True:
        raise err("OPS_UPLOAD_BLOCKED", f"Admin has blocked uploads by Ops on '{field.label}'.",
                  403)


def booking_media(request, booking_id) -> list[dict]:
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
    booking = writable_booking(request, data.get("booking"), moved_ok=True)   # a new own upload
    manager = is_manager(user, request)
    # a closed booking takes files only for an expert's work that has not arrived yet (done
    # offline before it was cancelled, or before Ops moved it and the other expert finished):
    # never anything added to an inspection already submitted
    closed = booking.stage == "cancelled" or (booking.stage == "completed" and not manager)
    if closed and (manager or booking.inspections.filter(
            expert=user, status__in=("submitted", "superseded")).exists()):
        raise err("BOOKING_CLOSED", f"A {booking.stage} {word(user)} takes no new files.", 409)
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
    if kind == "file" and ctype not in set().union(
            *(FILE_TYPES[a] for a in field.config.get("allowed", ["image", "pdf"]))):
        raise err("INVALID_CONTENT_TYPE", f"'{field.label}' does not take {ctype}.")
    replaces = data.get("replaces")
    if manager:      # Ops: the limit is what the submitted answers hold (checked again on attach)
        check_ops_upload(booking, field, user)
        _, _, ids = submitted_answer(booking, field)
        if replaces is not None and str(replaces) not in ids:
            raise err("UNKNOWN_MEDIA", "The file to replace is not on this field.")
        # places held by files that never arrived can be taken over, one upload each
        if replaces is None and len(ids) - len(unarrived(booking, ids)) >= max_count(field):
            raise err("TOO_MANY", f"'{field.label}' takes at most {max_count(field)}. "
                      "Replace one instead.", 409)
        # uploads not (yet) in the answers: a few may be left by closed tabs, never a pile
        loose = MediaAsset.objects.filter(booking=booking, field_key=field.key, uploaded_by=user,
                                          replaced_at__isnull=True).exclude(pk__in=ids) \
            .exclude(status="failed").count()
        if loose >= LOOSE_LIMIT:
            raise err("TOO_MANY", "Too many uploads on this field are not saved yet. Wait for "
                      "them to finish, or reload the page.", 409)
    elif replaces is not None:
        raise err("UNKNOWN_MEDIA", "Only Ops replace a file.")
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
            raise err("TOO_MANY", f"'{field.key}' takes at most {max_count(field)}.", 409)
        asset = MediaAsset(client_uuid=client_uuid, booking=booking, uploaded_by=user,
                           field_key=field.key, kind=kind, content_type=ctype, size=size,
                           sha256=sha, source=source)
        asset.key = f"bookings/{booking.id}/{asset.id}"
        asset.upload_id = storage.create_multipart(asset.key, ctype)
        asset.save()
    return _body(asset, True), True


def max_count(field: Field) -> int:
    if field.type == "signature":
        return 1
    return field.config.get("max_count", DEFAULT_MAX_COUNT.get(field.type, 1))


def submitted_answer(booking: Booking, field: Field, lock=False):
    """(inspection, part, file ids) of a field in the submitted inspection."""
    qs = booking.inspections.filter(status="submitted").order_by("-submitted_at")
    insp = (qs.select_for_update() if lock else qs).first()
    part = next((p for p, v in (insp.pinned() if insp else {}).items()
                 if v is not None and v.id == field.version_id), None)
    if insp is None or part is None:
        raise err("NOT_SUBMITTED", "Files can be added only after the expert submits.", 409)
    value = (insp.answers.get(part) or {}).get(field.key)
    return insp, part, [value] if isinstance(value, str) else list(value or [])


def live_asset(booking: Booking, field_key: str, asset_id) -> MediaAsset | None:
    """A file on this booking's field that has not been replaced."""
    try:
        return MediaAsset.objects.filter(booking=booking, field_key=field_key,
                                         replaced_at__isnull=True, pk=asset_id).first()
    except (ValueError, DjangoValidationError):     # not a UUID
        return None


NEVER_ARRIVED = ("pending", "uploaded", "failed")   # never checked in: not verified or purged


def unarrived(booking: Booking, ids: list[str]) -> list[str]:
    """Files a field names that never arrived (the expert's phone lost or broken), oldest first.
    Only while the job is waiting for its files; a file that arrived (even if later purged by the
    retention setting) never counts."""
    if booking.stage != "submitted":
        return []
    lost = set(map(str, MediaAsset.objects.filter(
        booking=booking, id__in=ids, status__in=NEVER_ARRIVED).values_list("id", flat=True)))
    return [i for i in ids if i in lost]


def first_unarrived(booking: Booking, ids: list[str]) -> str | None:
    return next(iter(unarrived(booking, ids)), None)


def attach(request, new: MediaAsset, replaces=None) -> None:
    """Ops put a file they uploaded into the submitted inspection: in place of `replaces` (kept as
    history, Admin can still open it) or added to the field. The report is rebuilt."""
    from apps.scoring import service as scoring

    user = request.user
    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=new.booking_id)
        new = MediaAsset.objects.select_for_update().get(pk=new.pk)
        field = field_for(booking, new.field_key)
        check_ops_upload(booking, field, user)
        if new.uploaded_by_id != user.pk or new.replaced_at is not None or new.status == "failed":
            raise err("UNKNOWN_MEDIA", "Upload the file first.")
        if new.status not in ("uploaded", "verified"):   # half-sent: must not push out a good one
            raise err("UPLOAD_NOT_FINISHED", "The file is still uploading.", 409)
        insp, part, ids = submitted_answer(booking, field, lock=True)
        answers = dict(insp.answers.get(part) or {})
        if str(new.id) in ids:
            return                                           # a retry: already in place
        old = None
        # an Ops "add" to a full field takes the place of a file that never arrived (a lost
        # phone), so the job can be finished; with room left it is simply added
        if replaces is None and len(ids) >= max_count(field):
            replaces = first_unarrived(booking, ids)
        if replaces is not None:
            old = live_asset(booking, field.key, replaces)
            if old is None or str(old.id) not in ids:
                raise err("UNKNOWN_MEDIA", "The file to replace is not on this field.")
            ids[ids.index(str(old.id))] = str(new.id)
        else:
            limit = max_count(field)
            if len(ids) >= limit:
                raise err("TOO_MANY",
                          f"'{field.label}' takes at most {limit}. Replace one instead.", 409)
            ids.append(str(new.id))
        answers[field.key] = ids
        insp.answers = {**insp.answers, part: answers}
        insp.row_version += 1
        insp.last_edited_by, insp.last_edited_at = user, timezone.now()
        insp.last_change = {"by": user.shown_name, "at": insp.last_edited_at.isoformat(),
                            "keys": [field.key]}
        insp.save()
        if old is not None:
            old.replaced_by, old.replaced_at = new, timezone.now()
            old.save(update_fields=["replaced_by", "replaced_at"])
        scoring.recompute(insp)
        MediaZip.objects.filter(booking=booking).delete()       # cached ZIPs no longer match
        activity.log(booking, user, "media_replaced" if old else "media_added",
                     {"media": [str(old.id) if old else None, str(new.id)]},
                     keys=[f"{part}.{field.key}"], inspection=insp)
        events.emit("inspection.updated", booking=str(booking.id), inspection=str(insp.id),
                    keys=[field.key])                     # the report is made again (handlers)
    check_completion(booking.id)     # a submitted booking now also waits for this file


def rebuild_report(booking_id) -> None:
    from apps.reports.tasks import render_report

    core_tasks.after_commit(lambda: render_report.delay(str(booking_id)))


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
    try:
        storage.complete_multipart(asset.key, asset.upload_id, parts)
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") != "NoSuchUpload":
            raise
        asset.refresh_from_db()          # a parallel request finished it first
        if asset.status in ("uploaded", "verified"):
            return asset
        raise err("NOT_UPLOADING", "Start the upload again.", 409) from e
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
    ids: set[str] = set()
    for part, version in inspection.pinned().items():
        if version is not None:
            ids |= set(referenced_ids(version, inspection.answers.get(part) or {}))
    return ids


def check_completion(booking_id) -> bool:
    """Submitted -> Completed once every referenced file is verified. Exactly once."""
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
        activity.log(b, None, "changed", {"stage": ["submitted", "completed"]})
    events.emit("inspection.completed", booking=str(b.id), booking_id=b.booking_id,
                inspection=str(insp.id))
    events.emit("media.completed", booking=str(b.id), booking_id=b.booking_id)
    return True


def remove(request, asset: MediaAsset) -> None:
    """Nobody deletes a submitted file (Ops replace it instead). Anyone may only take back a file
    they uploaded themselves that no submitted inspection uses yet (the expert's Remove button, an
    Ops upload that was never attached), so a retake is never blocked by an unwanted file."""
    user = request.user
    booking = asset.booking
    used = any(str(asset.id) in json.dumps(i.answers) for i in booking.inspections.filter(
        status="submitted"))
    mine_unused = asset.uploaded_by_id == user.pk and not used and asset.replaced_at is None
    if not mine_unused or (booking.stage in ("completed", "cancelled")
                           and not is_manager(user, request)):
        raise err("DELETE_NOT_ALLOWED", "You can only take back your own file before it is "
                  "submitted.", 403)
    delete_asset(user, asset)


def delete_asset(actor, asset: MediaAsset) -> None:
    """Ops remove a file after submission: the object, its preview, its reference in the answers."""
    from apps.scoring import service as scoring

    with transaction.atomic():
        for insp in asset.booking.inspections.select_for_update().all():
            changed = False
            for part in PARTS:
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
                insp.last_change = {"by": actor.shown_name, "at": insp.last_edited_at.isoformat(),
                                    "keys": [asset.field_key]}
                insp.save()
                scoring.recompute(insp)
        MediaZip.objects.filter(booking=asset.booking).delete()   # cached ZIPs no longer match
        keys, upload = [k for k in (asset.key, asset.preview_key) if k], asset.upload_id
        asset.delete()

        def clean_storage():                  # only once the database change is really saved
            for key in keys:
                storage.delete(key)
            if upload:
                storage.abort_multipart(asset.key, upload)

        core_tasks.after_commit(clean_storage)
    events.emit("media.deleted", booking=str(asset.booking_id), field_key=asset.field_key)
    check_completion(asset.booking_id)        # the removed file may have been the one holding it up


def stuck_uploads(hours: int | None = None):
    cutoff = timezone.now() - timedelta(hours=hours or settings.STUCK_UPLOAD_HOURS)
    return MediaAsset.objects.exclude(status__in=("verified", "purged")) \
        .filter(created_at__lt=cutoff)


def missing_files(booking: Booking) -> list[dict]:
    """What holds a submitted job back: per field of the counted inspection, the files it names
    that have not arrived, and whether the field is required (Ops upload those before finishing)."""
    from apps.forms.rules import evaluate_form, spec_from_version

    insp = booking.inspections.filter(status="submitted").order_by("-submitted_at").first()
    if booking.stage != "submitted" or insp is None:
        return []
    arrived = set(map(str, MediaAsset.objects.filter(booking=booking, status="verified")
                      .values_list("id", flat=True)))
    today = timezone.localdate().isoformat()
    rows = []
    pinned = insp.pinned()
    for part in ("start", "inspection", "end"):     # page order: check-in, inspection, wrap-up
        version = pinned.get(part)
        if version is None:
            continue
        answers = insp.answers.get(part) or {}
        required = evaluate_form(spec_from_version(version), insp.answers, today).required
        for f in Field.objects.filter(version=version, type__in=KINDS).order_by("order", "id"):
            value = answers.get(f.key)
            gone = [i for i in ([value] if isinstance(value, str) else value or [])
                    if str(i) not in arrived]
            if gone:
                rows.append({"part": part, "key": f.key, "label": f.label, "count": len(gone),
                             "required": bool(required.get(f.key))})
    return rows


def finish_without_missing(actor, booking: Booking) -> Booking:
    """Ops finish a job whose expert's files will not come (a lost phone): only once every
    required field has its file. Missing optional files are left out of the report; if they
    arrive later they are added and the report is made again (verify_asset)."""
    with transaction.atomic():
        b = Booking.objects.select_for_update().get(pk=booking.pk)
        if b.stage != "submitted":
            raise err("INVALID_STAGE", "Only a booking waiting for its files can be finished.", 409)
        rows = missing_files(b)
        need = [r for r in rows if r["required"]]
        if need:
            raise err("REQUIRED_FILES_MISSING", "Upload the required files first: "
                      + ", ".join(r["label"] for r in need) + ".", 409,
                      keys=[f"{r['part']}.{r['key']}" for r in need])
        insp = b.inspections.filter(status="submitted").order_by("-submitted_at").first()
        b.stage = "completed"
        b.row_version += 1
        b.last_change = {"by": actor.shown_name, "at": timezone.now().isoformat(),
                         "keys": ["stage"]}
        b.save()
        left = sum(r["count"] for r in rows)
        activity.log(b, actor, "finished_without_files",
                     {"stage": ["submitted", "completed"], "missing": left},
                     keys=["stage", *(f"{r['part']}.{r['key']}" for r in rows)], inspection=insp)
    events.emit("inspection.completed", booking=str(b.id), booking_id=b.booking_id,
                inspection=str(insp.id) if insp else "")
    return b
