"""Start, submit and Ops edits of inspections, including the offline conflict rules."""
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core import events
from apps.core import tasks as core_tasks
from apps.forms.access import STAGES, levels_for, may_see_submissions
from apps.forms.models import PARTS, Field, Form, FormType, FormVersion, VersionStatus
from apps.forms.rules import validate_answers
from apps.forms.serializers import VersionTreeSerializer
from apps.scoring import service as scoring

from . import activity, timing
from .models import Booking, Inspection
from .services import (
    _changed,
    _lock,
    active_inspection_type,
    booking_form_version,
    err,
    sync_columns,
    today,
)


def latest_published(form) -> FormVersion | None:
    return form.versions.filter(status=VersionStatus.PUBLISHED).order_by("-number").first()


def inspection_version(inspection_type: str) -> FormVersion:
    form = Form.objects.filter(type=FormType.CUSTOM, is_active=True,
                               inspection_type=inspection_type).first()
    version = latest_published(form) if form else None
    if version is None:
        raise err("NO_INSPECTION_FORM", f"No published inspection form for '{inspection_type}'.",
                  409)
    return version


def system_version(form_type: str) -> FormVersion | None:
    """The live version of the start or end form (None while it has not been published)."""
    form = Form.objects.filter(type=form_type).first()
    return latest_published(form) if form else None


def versions_to_pin(version: FormVersion) -> dict:
    """The versions one inspection goes through: its custom form's, plus the live start / end
    forms when the custom version begins / ends with them."""
    return {"inspection": version,
            "start": system_version(FormType.START) if version.use_start else None,
            "end": system_version(FormType.END) if version.use_end else None}


def current_versions(booking: Booking) -> dict:
    """What a booking's file uploads and reports are measured against: the pinned versions of its
    latest inspection, or, before anyone started, what a new inspection would pin."""
    insp = booking.inspections.select_related("form_version", "start_version",
                                              "end_version").order_by("-created_at").first()
    return insp.pinned() if insp else versions_to_pin(inspection_version(booking.inspection_type))


class _Role:
    """Just a role name, so the visibility rule can be asked about a role without a user."""
    def __init__(self, role: str):
        self.role = role


def own_filter(user) -> Q:
    """Bookings an expert may see: assigned to them, or where they still hold a draft."""
    return Q(assigned_expert_id=user.pk) | Q(inspections__expert_id=user.pk,
                                             inspections__status="draft")


def form_for_role(version: FormVersion, role: str, stage: str) -> dict:
    """The version tree an expert fills in: hidden fields removed, each field tagged with the
    caller's access level."""
    levels = levels_for(version, role, stage)
    tree: dict = dict(VersionTreeSerializer(version).data)
    pages = []
    for page in tree["pages"]:
        sections = []
        for section in page["sections"]:
            fields = [{**f, "level": levels[f["key"]]} for f in section["fields"]
                      if levels.get(f["key"]) != "hidden"]
            if fields:
                sections.append({**section, "fields": fields})
        if sections:
            pages.append({**page, "sections": sections})
    tree = {**tree, "pages": pages}
    if role == "expert":
        tree.pop("rating_config", None)     # experts must not learn how ratings are computed
    return tree


def check_shape(answers) -> None:
    """answers must be {"inspection": {...}, "start": {...}, "end": {...}} (every part optional)."""
    if not isinstance(answers, dict) or any(
            answers.get(k) is not None and not isinstance(answers[k], dict) for k in PARTS):
        raise err("INVALID_ANSWERS",
                  "answers must look like {inspection: {...}, start: {...}, end: {...}}.")


def _alert(b: Booking, code: str, detail: str) -> None:
    b.alerts = [*b.alerts, {"code": code, "detail": detail, "at": timezone.now().isoformat()}]


@transaction.atomic
def start(actor, b: Booking, client_uuid, client_started_at, inspection_type, app_version,
          start_answers=None):
    b = _lock(b)
    existing = Inspection.objects.filter(client_start_uuid=client_uuid).first()
    if existing is not None:
        if existing.booking_id != b.id or existing.expert_id != actor.pk:
            raise err("UUID_CONFLICT", "That request ID belongs to another request.", 409)
        return b, existing
    if app_version is not None and app_version < settings.MIN_APP_VERSION:
        raise err("APP_TOO_OLD", "Update the app to start new jobs.", 426)
    if b.assigned_expert_id != actor.pk:
        raise err("NOT_ASSIGNED", "This job is no longer assigned to you.", 409)
    if b.stage == "in_progress":
        # the expert's phone lost its saved session (new device, cleared storage): hand back
        # their own open inspection so they can carry on instead of being locked out
        mine = Inspection.objects.filter(booking=b, expert=actor, status="draft").last()
        if mine is None:
            raise err("ALREADY_STARTED", "This job is already started.", 409)
        return b, mine
    if b.stage != "assigned":
        raise err("INVALID_STAGE", f"A {b.stage} job cannot be started.", 409)
    changes = {"stage": ["assigned", "in_progress"]}
    if inspection_type is not None and inspection_type != b.inspection_type:
        # the expert physically started this type offline: it wins over Ops' later change
        if not isinstance(inspection_type, str) or not active_inspection_type(inspection_type):
            raise err("INVALID_TYPE", "Unknown inspection type.")
        changes["inspection_type"] = [b.inspection_type, inspection_type]
        _alert(b, "TYPE_CHANGE_REJECTED",
               f"Type change to {b.inspection_type} rejected: expert started {inspection_type}")
        events.emit("alert.type_change_rejected", booking=str(b.id), booking_id=b.booking_id)
        b.answers = {**b.answers, "inspection_type": inspection_type}
        sync_columns(b)
    pinned = versions_to_pin(inspection_version(b.inspection_type))
    if pinned["start"] is not None:
        # a job is only "in progress" once the check-in is done (nothing changes if it is not)
        check_shape({"start": start_answers})
        _clean_all(b, {**pinned, "inspection": None, "end": None}, {"start": start_answers or {}})
    b.stage, b.started_at = "in_progress", timezone.now()
    timing.stamp_late(b)
    insp = Inspection.objects.create(booking=b, expert=actor, form_version=pinned["inspection"],
                                     start_version=pinned["start"], end_version=pinned["end"],
                                     client_start_uuid=client_uuid,
                                     client_started_at=client_started_at)
    _changed(actor, b, changes)
    events.emit("inspection.started", booking=str(b.id), inspection=str(insp.id))
    return b, insp


def stamp_auto(version: FormVersion | None, answers: dict) -> dict:
    """Date and time fields set to 'automatic' that the phone did not fill in are stamped with
    the server's own time, so a missing or tampered value never leaves them empty."""
    if version is None:
        return answers
    now = timezone.localtime()
    stamp = {"date": now.date().isoformat(), "time": now.strftime("%H:%M"),
             "datetime": now.isoformat(timespec="seconds")}
    out = dict(answers)
    for f in Field.objects.filter(version=version, type__in=stamp):
        if f.config.get("auto") and not out.get(f.key):
            out[f.key] = stamp[f.type]
    return out


def _clean_all(b: Booking, pinned: dict, answers: dict):
    """Validate each part against the version it was started on. A part with no version (its
    form is not used) holds no answers. Returns (cleaned by part, errors)."""
    raw = {part: answers.get(part) or {} for part in PARTS}
    cleaned: dict[str, dict] = {}
    errors: dict = {}
    unused = [part for part, v in pinned.items() if v is None and raw[part]]
    if unused:
        raise err("INVALID_ANSWERS", "This inspection does not use that form.",
                  errors={k: "NOT_USED" for part in unused for k in raw[part]})
    for part in PARTS:
        version = pinned[part]
        if version is None:
            cleaned[part] = {}
            continue
        context = {"booking": b.answers, **{p: (cleaned.get(p) or raw[p]) for p in PARTS}}
        cleaned[part], e = validate_answers(version, {**context, part: raw[part]}, today())
        errors = {**errors, **e}
    from apps.media.services import reference_errors

    errors = {**errors, **reference_errors(
        b, [(pinned[p], cleaned[p]) for p in PARTS if pinned[p] is not None])}
    if errors:
        raise err("INVALID_ANSWERS", "Some answers are invalid.", errors=errors)
    return cleaned


def _locked_keys(role: str, stage: str, pinned: dict, answers: dict, old: dict) -> list[str]:
    """Keys the role may not change at this stage (unknown keys are left to validation)."""
    locked: list[str] = []
    for key, v in pinned.items():
        if v is None:
            continue
        levels = levels_for(v, role, stage)
        # hidden: always refused (no value oracle); view-only: refused only if it changes
        locked += [k for k, val in (answers.get(key) or {}).items()
                   if k in levels and (levels[k] == "hidden" or (
                       levels[k] != "edit" and val != (old.get(key) or {}).get(k)))]
    return sorted(locked)


@transaction.atomic
def submit(actor, b: Booking, submission_uuid, answers: dict, form_version_id=None):
    check_shape(answers)
    b = _lock(b)
    done = Inspection.objects.filter(client_submission_uuid=submission_uuid).first()
    if done is not None:
        if done.booking_id != b.id or done.expert_id != actor.pk:
            raise err("UUID_CONFLICT", "That request ID belongs to another request.", 409)
        return b, done
    insp = b.inspections.filter(expert=actor, status="draft").first()
    if insp is None:
        # an offline start that never reached us: the phone names its pinned version, but it must
        # belong to the form that handles this booking's type (no shopping for a weaker form)
        form = Form.objects.filter(type=FormType.CUSTOM, is_active=True,
                                   inspection_type=b.inspection_type).first()
        version = (FormVersion.objects.filter(pk=form_version_id, form=form,
                                              status=VersionStatus.PUBLISHED).first()
                   if form_version_id and form else None)
        if version is None:
            raise err("NOT_STARTED", "Start the inspection first.", 409)
        pinned = versions_to_pin(version)
        insp = Inspection.objects.create(booking=b, expert=actor, form_version=version,
                                         start_version=pinned["start"],
                                         end_version=pinned["end"])
    pinned = insp.pinned()
    locked = _locked_keys(actor.role, "in_progress", pinned, answers, {})
    if locked:
        raise err("FIELD_ACCESS", "You cannot change these fields.", 403, keys=locked)
    answers = {p: stamp_auto(pinned[p], answers.get(p) or {}) for p in PARTS}
    insp.answers = _clean_all(b, pinned, answers)
    insp.status, insp.submitted_at = "submitted", timezone.now()
    insp.client_submission_uuid = submission_uuid
    insp.save()
    scoring.recompute(insp)
    _advance(actor, b, insp)
    events.emit("inspection.submitted", booking=str(b.id), inspection=str(insp.id))
    from apps.media.services import check_completion

    check_completion(b.id)       # nothing left to wait for -> Completed right away
    b.refresh_from_db()
    return b, insp


def _advance(actor, b: Booking, insp: Inspection) -> None:
    changes: dict = {}
    if b.stage == "cancelled":
        pass                                          # kept on the cancelled booking
    elif b.assigned_expert_id != actor.pk:            # reassigned while the expert worked offline
        other_started = b.inspections.filter(expert_id=b.assigned_expert_id,
                                             status="draft").exists()
        b.conflict = "TWO_EXPERTS"
        _alert(b, "CONFLICT_TWO_EXPERTS", "Two experts inspected this booking.")
        events.emit("alert.conflict", booking=str(b.id), booking_id=b.booking_id,
                    code="CONFLICT_TWO_EXPERTS")
        if not other_started:
            b.withdrawn_expert_id = b.assigned_expert_id
            b.assigned_expert = actor
            changes = {"stage": [b.stage, "submitted"]}
            b.stage = "submitted"
    elif b.stage in ("in_progress", "assigned"):
        if b.stage == "assigned" and b.released_draft_expected:
            b.conflict = "RELEASED_DRAFT_ARRIVED"
            _alert(b, "RELEASED_DRAFT_ARRIVED", "A force-released draft was submitted.")
            events.emit("alert.conflict", booking=str(b.id), booking_id=b.booking_id,
                        code="RELEASED_DRAFT_ARRIVED")
        b.released_draft_expected = False
        changes = {"stage": [b.stage, "submitted"]}
        b.stage = "submitted"
        timing.stamp_duration(b, insp.submitted_at)
    b.chassis_no = (insp.answers.get("inspection") or {}).get("chassis_no", "")
    _changed(actor, b, changes or {"inspection": [None, str(insp.id)]})


def _dropped_files(pinned, old: dict, new: dict, changed) -> list[str]:
    """Photo, video, file and signature answers that lost a file id in this edit."""
    from apps.media.models import KINDS

    def ids(v):
        return {v} if isinstance(v, str) else set(v or [])

    out = []
    for part, k in changed:
        version = pinned.get(part)
        if version is not None and Field.objects.filter(version=version, key=k,
                                                        type__in=KINDS).exists() \
                and not ids((old.get(part) or {}).get(k)) <= ids(new[part].get(k)):
            out.append(f"{part}.{k}")
    return out


@transaction.atomic
def edit_inspection(actor, insp: Inspection, answers: dict, row_version: int) -> Inspection:
    check_shape(answers)
    insp = Inspection.objects.select_for_update().get(pk=insp.pk)
    if row_version != insp.row_version:
        raise err("STALE_INSPECTION", "Someone changed this inspection since you opened it.", 409,
                  changed_by=insp.last_change.get("by"), changed_at=insp.last_change.get("at"),
                  changed_keys=insp.last_change.get("keys", []), row_version=insp.row_version)
    b = insp.booking
    pinned = insp.pinned()
    locked = _locked_keys(actor.role, b.stage, pinned, answers, insp.answers)
    if locked:
        raise err("FIELD_ACCESS", "You cannot change these fields at this stage.", 403, keys=locked)
    merged = {k: {**(insp.answers.get(k) or {}), **(answers.get(k) or {})} for k in PARTS}
    new = _clean_all(b, pinned, merged)
    changed = [(part, k) for part in PARTS
               for k in sorted(set(new[part]) | set(insp.answers.get(part) or {}))
               if new[part].get(k) != (insp.answers.get(part) or {}).get(k)]
    dropped = _dropped_files(pinned, insp.answers, new, changed)
    if dropped:          # nobody deletes a submitted file: Ops replace it on the Media tab
        raise err("FILE_REMOVAL_NOT_ALLOWED", "Files cannot be removed. Replace them on the "
                  "Media tab instead.", 403, keys=dropped)
    keys = sorted(k for _, k in changed)
    if keys:
        insp.answers = new
        insp.row_version += 1
        insp.last_edited_by, insp.last_edited_at = actor, timezone.now()
        insp.last_change = {"by": actor.username, "at": insp.last_edited_at.isoformat(),
                            "keys": keys}
        insp.save()
        scoring.recompute(insp)
        chassis = new["inspection"].get("chassis_no")
        if chassis is not None and b.chassis_no != chassis:
            Booking.objects.filter(pk=b.pk).update(chassis_no=chassis)
        activity.log(b, actor, "inspection_edited", keys=[f"{p}.{k}" for p, k in changed],
                     inspection=insp)
        events.emit("inspection.updated", booking=str(b.id), inspection=str(insp.id), keys=keys)
    return insp


BOOKING_SEARCH = {"booking_id": "booking_id", "customer_name": "customer_name",
                  "car_make_model": "car_make_model", "customer_phone": "customer_phone"}


def searchable_stages(role: str) -> dict[str, list[str]]:
    """{column: stages} where the role may see that field. A search only matches a column on
    bookings at those stages, so it can never confirm a value the role may not see."""
    columns = [*BOOKING_SEARCH, "chassis_no"]
    if role == "admin":
        return {c: list(STAGES) for c in columns}
    try:
        booking_version = booking_form_version()
    except Exception:  # noqa: BLE001 - no booking form yet means no bookings either
        return {}
    by_stage = {s: levels_for(booking_version, role, s) for s in STAGES}
    out = {c: [s for s in STAGES if by_stage[s].get(key, "hidden") != "hidden"]  # fail closed
           for c, key in BOOKING_SEARCH.items()}
    versions = [v for f in Form.objects.filter(type=FormType.CUSTOM, is_active=True)
                if (v := latest_published(f))]
    chassis = {s: [levels_for(v, role, s).get("chassis_no", "hidden") for v in versions]
               or ["hidden"] for s in STAGES}                    # no form to say: closed
    out["chassis_no"] = [s for s in STAGES if "hidden" not in chassis[s]]
    if any(not may_see_submissions(_Role(role), f) for f in Form.objects.filter(
            type=FormType.CUSTOM)):
        out["chassis_no"] = []                  # a hidden submission must not be searchable
    return out


@transaction.atomic
def set_overrides(actor, insp: Inspection, body: dict, row_version: int) -> Inspection:
    insp = Inspection.objects.select_for_update().get(pk=insp.pk)
    if row_version != insp.row_version:
        raise err("STALE_INSPECTION", "Someone changed this inspection since you opened it.", 409,
                  changed_by=insp.last_change.get("by"), changed_at=insp.last_change.get("at"),
                  changed_keys=insp.last_change.get("keys", []), row_version=insp.row_version)
    try:
        scoring.validate_overrides(insp.form_version, body)
    except ValueError as e:
        raise err("INVALID_OVERRIDES", str(e)) from e
    insp.overrides = scoring.apply_overrides(insp.overrides, body)
    insp.row_version += 1
    insp.last_edited_by, insp.last_edited_at = actor, timezone.now()
    insp.last_change = {"by": actor.username, "at": insp.last_edited_at.isoformat(),
                        "keys": ["overrides"]}
    insp.save()
    scoring.recompute(insp)
    activity.log(insp.booking, actor, "ratings_changed", keys=[], inspection=insp)
    events.emit("inspection.updated", booking=str(insp.booking_id), inspection=str(insp.id),
                keys=["overrides"])
    return insp


@transaction.atomic
def resolve_conflict(actor, b: Booking, inspection_id) -> Booking:
    """Two experts inspected one booking: Ops keep one inspection. The other is set aside
    ("superseded"), never deleted, and the booking carries on with the kept one."""
    b = _lock(b)
    if not b.conflict:
        raise err("NO_CONFLICT", "This booking has no conflict to resolve.", 409)
    keep = b.inspections.filter(pk=inspection_id, status="submitted").first()
    if keep is None:
        raise err("INVALID_INSPECTION", "Choose one of this booking's submitted inspections.")
    b.inspections.filter(status="submitted").exclude(pk=keep.pk).update(status="superseded")
    changes: dict = {"conflict": [b.conflict, ""],
                     "inspection": [None, str(keep.id)]}
    if b.assigned_expert_id != keep.expert_id:
        changes["assigned_expert"] = [b.assigned_expert_id, keep.expert_id]
    b.conflict, b.withdrawn_expert = "", None
    b.assigned_expert = keep.expert
    if b.stage in ("assigned", "in_progress"):
        changes["stage"] = [b.stage, "submitted"]
        b.stage = "submitted"
    b.chassis_no = (keep.answers.get("inspection") or {}).get("chassis_no", "")
    _changed(actor, b, changes)
    scoring.recompute(keep)
    events.emit("inspection.updated", booking=str(b.id), inspection=str(keep.id),
                keys=["conflict_resolved"])
    from apps.media.services import check_completion

    core_tasks.after_commit(lambda: check_completion(b.id))
    return b
