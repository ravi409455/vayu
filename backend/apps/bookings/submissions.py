"""Start, submit and Ops edits of inspections, including the offline conflict rules."""
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core import events
from apps.forms.access import STAGES, levels_for
from apps.forms.models import Form, FormKind, FormVersion, VersionStatus
from apps.forms.rules import validate_answers
from apps.forms.serializers import VersionTreeSerializer
from apps.scoring import service as scoring

from .models import Booking, Inspection
from .services import _changed, _lock, active_item, booking_form_version, err, sync_columns, today


def latest_published(form) -> FormVersion | None:
    return form.versions.filter(status=VersionStatus.PUBLISHED).order_by("-number").first()


def inspection_version(inspection_type: str) -> FormVersion:
    form = Form.objects.filter(kind=FormKind.INSPECTION, is_active=True,
                               inspection_type=inspection_type).first()
    version = latest_published(form) if form else None
    if version is None:
        raise err("NO_INSPECTION_FORM", f"No published inspection form for '{inspection_type}'.",
                  409)
    return version


def ops_version() -> FormVersion | None:
    form = Form.objects.filter(kind=FormKind.OPS, is_active=True).first()
    return latest_published(form) if form else None


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
    """answers must be {"inspection": {...}, "ops": {...}} (either part optional)."""
    if not isinstance(answers, dict) or any(
            answers.get(k) is not None and not isinstance(answers[k], dict)
            for k in ("inspection", "ops")):
        raise err("INVALID_ANSWERS", "answers must look like {inspection: {...}, ops: {...}}.")


def _alert(b: Booking, code: str, detail: str) -> None:
    b.alerts = [*b.alerts, {"code": code, "detail": detail, "at": timezone.now().isoformat()}]


@transaction.atomic
def start(actor, b: Booking, client_uuid, client_started_at, inspection_type, app_version):
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
        raise err("ALREADY_STARTED", "This job is already started.", 409)
    if b.stage != "assigned":
        raise err("INVALID_STAGE", f"A {b.stage} job cannot be started.", 409)
    changes = {"stage": ["assigned", "in_progress"]}
    if inspection_type is not None and inspection_type != b.inspection_type:
        # the expert physically started this type offline: it wins over Ops' later change
        if not isinstance(inspection_type, str) or not active_item("inspection_type",
                                                                    inspection_type):
            raise err("INVALID_TYPE", "Unknown inspection type.")
        changes["inspection_type"] = [b.inspection_type, inspection_type]
        _alert(b, "TYPE_CHANGE_REJECTED",
               f"Type change to {b.inspection_type} rejected: expert started {inspection_type}")
        events.emit("alert.type_change_rejected", booking=str(b.id), booking_id=b.booking_id)
        b.answers = {**b.answers, "inspection_type": inspection_type}
        sync_columns(b)
    version = inspection_version(b.inspection_type)
    b.stage, b.started_at = "in_progress", timezone.now()
    insp = Inspection.objects.create(booking=b, expert=actor, form_version=version,
                                     client_start_uuid=client_uuid,
                                     client_started_at=client_started_at)
    _changed(actor, b, changes)
    events.emit("inspection.started", booking=str(b.id), inspection=str(insp.id))
    return b, insp


def _clean_both(b: Booking, version: FormVersion, answers: dict):
    ans_i, ans_o = answers.get("inspection") or {}, answers.get("ops") or {}
    cleaned_i, errors = validate_answers(
        version, {"inspection": ans_i, "booking": b.answers, "ops": ans_o}, today())
    cleaned_o: dict = {}
    ov = ops_version()
    if ov is not None:
        cleaned_o, e2 = validate_answers(
            ov, {"ops": ans_o, "booking": b.answers, "inspection": cleaned_i}, today())
        errors = {**errors, **e2}
    from apps.media.services import reference_errors

    errors = {**errors, **reference_errors(b, [(version, cleaned_i), (ov, cleaned_o)])}
    if errors:
        raise err("INVALID_ANSWERS", "Some answers are invalid.", errors=errors)
    return cleaned_i, cleaned_o, ov


def _locked_keys(role: str, stage: str, version, ops_v, answers: dict, old: dict) -> list[str]:
    """Keys the role may not change at this stage (unknown keys are left to validation)."""
    locked: list[str] = []
    for v, key in ((version, "inspection"), (ops_v, "ops")):
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
        form = Form.objects.filter(kind=FormKind.INSPECTION, is_active=True,
                                   inspection_type=b.inspection_type).first()
        version = (FormVersion.objects.filter(pk=form_version_id, form=form,
                                              status=VersionStatus.PUBLISHED).first()
                   if form_version_id and form else None)
        if version is None:
            raise err("NOT_STARTED", "Start the inspection first.", 409)
        insp = Inspection.objects.create(booking=b, expert=actor, form_version=version)
    version = insp.form_version
    ov = ops_version()
    locked = _locked_keys(actor.role, "in_progress", version, ov, answers, {})
    if locked:
        raise err("FIELD_ACCESS", "You cannot change these fields.", 403, keys=locked)
    cleaned_i, cleaned_o, _ = _clean_both(b, version, answers)
    insp.answers = {"inspection": cleaned_i, "ops": cleaned_o}
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
    b.chassis_no = (insp.answers.get("inspection") or {}).get("chassis_no", "")
    _changed(actor, b, changes or {"inspection": [None, str(insp.id)]})


@transaction.atomic
def edit_inspection(actor, insp: Inspection, answers: dict, row_version: int) -> Inspection:
    check_shape(answers)
    insp = Inspection.objects.select_for_update().get(pk=insp.pk)
    if row_version != insp.row_version:
        raise err("STALE_INSPECTION", "Someone changed this inspection since you opened it.", 409,
                  changed_by=insp.last_change.get("by"), changed_at=insp.last_change.get("at"),
                  changed_keys=insp.last_change.get("keys", []), row_version=insp.row_version)
    b = insp.booking
    version, ov = insp.form_version, ops_version()
    locked = _locked_keys(actor.role, b.stage, version, ov, answers, insp.answers)
    if locked:
        raise err("FIELD_ACCESS", "You cannot change these fields at this stage.", 403, keys=locked)
    merged = {k: {**(insp.answers.get(k) or {}), **(answers.get(k) or {})}
              for k in ("inspection", "ops")}
    cleaned_i, cleaned_o, _ = _clean_both(b, version, merged)
    new = {"inspection": cleaned_i, "ops": cleaned_o}
    keys = sorted(k for part in ("inspection", "ops") for k in set(new[part]) | set(
        insp.answers.get(part) or {}) if new[part].get(k) != (insp.answers.get(part) or {}).get(k))
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
    versions = [v for f in Form.objects.filter(kind=FormKind.INSPECTION, is_active=True)
                if (v := latest_published(f))]
    chassis = {s: [levels_for(v, role, s).get("chassis_no", "hidden") for v in versions]
               or ["hidden"] for s in STAGES}                    # no form to say: closed
    out["chassis_no"] = [s for s in STAGES if "hidden" not in chassis[s]]
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
    events.emit("inspection.updated", booking=str(insp.booking_id), inspection=str(insp.id),
                keys=["overrides"])
    return insp
