"""Start, submit and Ops edits of inspections, including the offline conflict rules."""
from datetime import timedelta
from typing import NoReturn

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
from .changes import check_fresh, stamp
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


# a job moved away stays deliverable for a week after its date, whatever its stage: work done
# offline still reaches Ops even if the other expert finished first or Ops cancelled it
MOVED_DAYS = 7


def deliver_filter(user) -> Q:
    """Bookings an expert may still send work for (check-in, answers, their own photos): their
    own, or one Ops moved away from them (the timeline says it was theirs), because they may
    have inspected it offline before they knew. What then happens is decided in _advance: back
    to them if the new expert has not started, else a conflict for Ops. Never used for lists."""
    recent = timezone.localdate() - timedelta(days=MOVED_DAYS)
    return own_filter(user) | Q(activity__changes__assigned_expert__0=user.pk,
                                inspection_date__gte=recent) | Q(
        # a draft Ops force-released may still arrive (then a conflict for Ops), as long as a job
        # moved away does
        inspections__expert_id=user.pk, inspections__status="released",
        inspection_date__gte=recent)


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
        tree.pop("key_checks", None)        # nor see the Key Checks Ops fill
    return tree


def check_shape(answers) -> None:
    """answers must be {"inspection": {...}, "start": {...}, "end": {...}} (every part optional)."""
    if not isinstance(answers, dict) or any(
            answers.get(k) is not None and not isinstance(answers[k], dict) for k in PARTS):
        raise err("INVALID_ANSWERS",
                  "answers must look like {inspection: {...}, start: {...}, end: {...}}.")


def _alert(b: Booking, code: str, detail: str) -> None:
    b.alerts = [*b.alerts, {"code": code, "detail": detail, "at": timezone.now().isoformat()}]


# a phone's clock may be a few minutes off the server's (it is corrected at each sync)
CLOCK_ALLOWANCE = timedelta(minutes=10)


class _OldVersion(Exception):
    """The phone filled a version that was already replaced when the expert started."""


def _replaced_by(version: FormVersion):
    """When the next published version of the same form came out (None: it is the latest)."""
    return (FormVersion.objects.filter(form_id=version.form_id, status=VersionStatus.PUBLISHED,
                                       number__gt=version.number)
            .order_by("number").values_list("published_at", flat=True).first())


def _was_latest(version: FormVersion, at) -> bool:
    """Was [version] the newest published version of its form at [at], give or take the clock
    allowance?"""
    newer = _replaced_by(version)
    return ((version.published_at or at) <= at + CLOCK_ALLOWANCE
            and (newer is None or newer > at - CLOCK_ALLOWANCE))


def _kept_notes(version: FormVersion) -> list[str]:
    """What Ops are told when work arrives on a version that is no longer the one a new start
    would get (each case is allowed, but rare enough to be looked at)."""
    notes = [] if version.form.is_active else ["the form was switched off since."]
    if _replaced_by(version) is not None:
        notes.append(f"version {version.number} kept: a newer one was published since.")
    return notes


def _named_version(raw, forms) -> FormVersion | None:
    """A published version of one of [forms] that the phone named (None when it named none)."""
    if raw is None:
        return None
    version = FormVersion.objects.filter(pk__in=[raw] if type(raw) is int else [], form__in=forms,
                                         status=VersionStatus.PUBLISHED).select_related("form")
    if not version:
        raise err("INVALID_VERSION", "That form version is not one this lead can use.")
    return version[0]


def phone_pins(b: Booking, named: dict, at) -> tuple[dict, list[str]]:
    """The versions a start pins. The phone names those it pinned when the expert started (offline
    perhaps): each is kept if it was the latest published at that time, else _OldVersion. When it
    names none (older apps), the latest. Returns (pinned, notes for Ops: see _kept_notes)."""
    custom = Form.objects.filter(type=FormType.CUSTOM, inspection_type=b.inspection_type)
    phone = _named_version(named.get("inspection"), custom)
    if phone is None:
        return versions_to_pin(inspection_version(b.inspection_type)), []
    # a start / end version is looked at only when this version goes through that form
    start_v = (_named_version(named.get("start"), Form.objects.filter(type=FormType.START))
               if phone.use_start else None)
    end_v = (_named_version(named.get("end"), Form.objects.filter(type=FormType.END))
             if phone.use_end else None)
    if not all(_was_latest(v, at) for v in (phone, start_v, end_v) if v is not None):
        raise _OldVersion
    return {"inspection": phone,
            "start": (start_v or system_version(FormType.START)) if phone.use_start else None,
            "end": (end_v or system_version(FormType.END)) if phone.use_end else None}, \
        _kept_notes(phone)


def _before_too_old(at) -> bool:
    """Was the phone's start before its app version became too old? The minimum only rises once a
    build that meets it exists, so work started before that build was published was started on an
    allowed app."""
    # ponytail: the first qualifying build's upload time is a lower bound for when the minimum
    # rose (that moment is not recorded); record it if work started in between gets refused
    from apps.notify.models import AppRelease

    first = (AppRelease.objects.filter(version_code__gte=settings.MIN_APP_VERSION)
             .order_by("created_at").values_list("created_at", flat=True).first())
    return first is not None and at < first


def _late_work(b: Booking, code: str, detail: str) -> None:
    """Ops are told about work that arrived late (alert on the booking, bell, push, webhook)."""
    _alert(b, code, detail)
    events.emit("alert.late_work", booking=str(b.id), booking_id=b.booking_id, code=code)


def start(actor, b: Booking, client_uuid, client_started_at, inspection_type, app_version,
          start_answers=None, versions=None):
    """[versions]: what the phone pinned when the expert started ({inspection, start, end} ids)."""
    try:
        return _start(actor, b, client_uuid, client_started_at, inspection_type, app_version,
                      start_answers, versions or {})
    except _OldVersion:
        _refuse_old(b)


def _refuse_old(b: Booking) -> NoReturn:
    with transaction.atomic():        # the refusal rolled the request back; the alert stays
        b = _lock(b)
        if "FORM_VERSION_REFUSED" not in [a["code"] for a in b.alerts]:    # retries: once
            _late_work(b, "FORM_VERSION_REFUSED",
                       "The expert filled a form version replaced before they started.")
            b.save(update_fields=["alerts"])
    raise err("FORM_VERSION_OLD", "This lead was filled on a form that had already been "
              "replaced. Ops have been told.", 409) from None


@transaction.atomic
def _start(actor, b: Booking, client_uuid, client_started_at, inspection_type, app_version,
           start_answers, versions: dict):
    b = _lock(b)
    existing = Inspection.objects.filter(client_start_uuid=client_uuid).first()
    if existing is not None:
        if existing.booking_id != b.id or existing.expert_id != actor.pk:
            raise err("UUID_CONFLICT", "That request ID belongs to another request.", 409)
        return b, existing
    # the phone's clock is trusted only back to when the booking existed: nobody started it before
    at = max(client_started_at or timezone.now(), b.created_at - CLOCK_ALLOWANCE)
    too_old = app_version is not None and app_version < settings.MIN_APP_VERSION
    if too_old and not _before_too_old(at):
        raise err("APP_TOO_OLD", "Update the app to start new leads.", 426)
    if b.assigned_expert_id != actor.pk:
        raise err("NOT_ASSIGNED", "This lead is no longer assigned to you.", 409)
    if b.stage == "in_progress":
        # the expert's phone lost its saved session (new device, cleared storage): hand back
        # their own open inspection so they can carry on instead of being locked out
        mine = Inspection.objects.filter(booking=b, expert=actor, status="draft").last()
        if mine is None:
            raise err("ALREADY_STARTED", "This lead is already started.", 409)
        return b, mine
    if b.stage != "assigned":
        raise err("INVALID_STAGE", f"A {b.stage} lead cannot be started.", 409)
    changes = {"stage": ["assigned", "in_progress"]}
    if inspection_type is not None and inspection_type != b.inspection_type:
        # the expert physically started this type offline: it wins over Ops' later change
        if not isinstance(inspection_type, str) or not active_inspection_type(inspection_type):
            raise err("INVALID_TYPE", "Unknown inspection type.")
        changes["inspection_type"] = [b.inspection_type, inspection_type]
        _alert(b, "TYPE_CHANGE_REJECTED",
               f"Type change to {b.inspection_type} rejected: expert started {inspection_type}")
        b.answers = {**b.answers, "inspection_type": inspection_type}
        sync_columns(b)
        b.save()                          # webhooks read the booking as it is now
        # after the type is the expert's: it goes to that type's integrations (F-239)
        events.emit("alert.type_change_rejected", booking=str(b.id), booking_id=b.booking_id)
    pinned, notes = phone_pins(b, versions, at)
    if notes:
        _late_work(b, "LATE_WORK", "Started offline; " + " ".join(notes))
    if too_old:
        _late_work(b, "LATE_WORK", f"Started on app version {app_version} before it had to be "
                   "updated.")
    checked_in: dict = {}
    if pinned["start"] is not None:
        # a job is only "in progress" once the check-in is done (nothing changes if it is not)
        check_shape({"start": start_answers})
        checked_in = _clean_all(b, {**pinned, "inspection": None, "end": None},
                                {"start": start_answers or {}})["start"]
    b.stage, b.started_at = "in_progress", timezone.now()
    timing.stamp_late(b)
    insp = Inspection.objects.create(booking=b, expert=actor, form_version=pinned["inspection"],
                                     start_version=pinned["start"], end_version=pinned["end"],
                                     client_start_uuid=client_uuid,
                                     client_started_at=client_started_at,
                                     # kept from now on: Ops see the arrival proof (F-241)
                                     answers={"start": checked_in} if checked_in else {})
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


def _clean_all(b: Booking, pinned: dict, answers: dict, kept: dict | None = None):
    """Validate each part against the version it was started on. A part with no version (its
    form is not used) holds no answers. [kept]: the answers stored before an Ops edit (see
    validate_answers). Returns (cleaned by part, errors)."""
    raw = {part: answers.get(part) or {} for part in PARTS}
    cleaned: dict[str, dict] = {}
    errors: dict = {}
    messages: dict = {}
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
        cleaned[part], e = validate_answers(version, {**context, part: raw[part]}, today(),
                                            kept=None if kept is None else kept.get(part) or {},
                                            messages=messages)
        errors = {**errors, **e}
    from apps.media.services import reference_errors

    errors = {**errors, **reference_errors(
        b, [(pinned[p], cleaned[p]) for p in PARTS if pinned[p] is not None])}
    if errors:
        raise err("INVALID_ANSWERS", "Some answers are invalid.", errors=errors,
                  messages={k: messages.get(k, v) for k, v in errors.items()})
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


def mark_unverified_time(b: Booking, insp: Inspection) -> None:
    """The phone says its clock was not checked when it stamped this work: once true, it stays
    true, for the inspection and its booking (F-222)."""
    Inspection.objects.filter(pk=insp.pk).update(unverified_time=True)
    Booking.objects.filter(pk=b.pk).update(unverified_time=True)


def submit(actor, b: Booking, submission_uuid, answers: dict, form_version_id=None):
    try:
        return _submit(actor, b, submission_uuid, answers, form_version_id)
    except _OldVersion:
        _refuse_old(b)


@transaction.atomic
def _submit(actor, b: Booking, submission_uuid, answers: dict, form_version_id):
    check_shape(answers)
    b = _lock(b)
    done = Inspection.objects.filter(client_submission_uuid=submission_uuid).first()
    if done is not None:
        if done.booking_id != b.id or done.expert_id != actor.pk:
            raise err("UUID_CONFLICT", "That request ID belongs to another request.", 409)
        return b, done
    # their open draft; else the one Ops force-released while they worked (it still counts)
    insp = (b.inspections.filter(expert=actor, status="draft").first()
            or b.inspections.filter(expert=actor, status="released").order_by("-created_at")
            .first())
    if insp is None and b.inspections.filter(expert=actor,
                                             status__in=("submitted", "superseded")).exists():
        # a new request id for work already sent (a reinstalled app): never a second inspection
        raise err("ALREADY_SUBMITTED", "Already submitted; Ops can edit it.", 409)
    if insp is None:
        # an offline start that never reached us: the phone names its pinned version, but it must
        # belong to a form that handles this booking's type (no shopping for another type's form)
        version = FormVersion.objects.filter(
            pk=form_version_id, status=VersionStatus.PUBLISHED, form__type=FormType.CUSTOM,
            form__inspection_type=b.inspection_type).select_related("form").first() \
            if form_version_id else None
        if version is None:
            raise err("NOT_STARTED", "Start the inspection first.", 409)
        # it must have been the latest at some moment since the booking existed (start unknown)
        replaced = _replaced_by(version)
        if replaced is not None and replaced <= b.created_at - CLOCK_ALLOWANCE:
            raise _OldVersion
        notes = _kept_notes(version)          # e.g. the form was switched off since (R-35)
        if notes:
            _late_work(b, "LATE_WORK", "Submitted without its start; " + " ".join(notes))
        pinned = versions_to_pin(version)
        insp = Inspection.objects.create(booking=b, expert=actor, form_version=version,
                                         start_version=pinned["start"],
                                         end_version=pinned["end"])
    pinned = insp.pinned()
    locked = _locked_keys(actor.role, "in_progress", pinned, answers, {})
    if locked:
        raise err("FIELD_ACCESS", "You cannot change these fields.", 403, keys=locked)
    # a submit without the check-in keeps the one sent at start
    if "start" not in answers:
        answers = {**answers, "start": (insp.answers or {}).get("start")}
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
        other = b.assigned_expert_id
        other_started = b.inspections.filter(expert_id=other,
                                             status__in=("draft", "submitted")).exists()
        if other_started:                             # two real inspections: Ops choose one
            b.conflict = "TWO_EXPERTS"
            _alert(b, "CONFLICT_TWO_EXPERTS", "Two experts inspected this booking.")
            events.emit("alert.conflict", booking=str(b.id), booking_id=b.booking_id,
                        code="CONFLICT_TWO_EXPERTS")
        else:                                         # the new expert never began: back to this one
            b.withdrawn_expert_id = other
            b.assigned_expert = actor
            b.answers = {**b.answers, "assigned_expert": actor.pk}
            changes = {"stage": [b.stage, "submitted"], "assigned_expert": [other, actor.pk]}
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


def _check_files(actor, b: Booking, pinned, old: dict, new: dict, changed) -> None:
    """Photo, video and file answers in an Ops edit: nobody removes a file (Ops replace it on the
    Media tab), and a file is added only under the same rules as on the Media tab, and only one
    the editor uploaded themselves."""
    from apps.media.models import KINDS, MediaAsset
    from apps.media.services import check_ops_upload

    def ids(v):
        return {v} if isinstance(v, str) else set(v or [])

    dropped = []
    for part, k in changed:
        version = pinned.get(part)
        f = version and Field.objects.filter(version=version, key=k, type__in=KINDS).first()
        if not f:
            continue
        before, after = ids((old.get(part) or {}).get(k)), ids(new[part].get(k))
        if not before <= after:
            dropped.append(f"{part}.{k}")
            continue
        added = after - before
        if added:
            check_ops_upload(b, f, actor)
            own = MediaAsset.objects.filter(booking=b, field_key=k, uploaded_by=actor,
                                            replaced_at__isnull=True, pk__in=added).count()
            if own != len(added):
                raise err("UNKNOWN_MEDIA", "Add only files you uploaded to this field.")
    if dropped:
        raise err("FILE_REMOVAL_NOT_ALLOWED", "Files cannot be removed. Replace them on the "
                  "Media tab instead.", 403, keys=dropped)


@transaction.atomic
def edit_inspection(actor, insp: Inspection, answers: dict, row_version: int) -> Inspection:
    check_shape(answers)
    insp = Inspection.objects.select_for_update().get(pk=insp.pk)
    check_fresh(insp, row_version, "STALE_INSPECTION", "inspection")
    b = insp.booking
    pinned = insp.pinned()
    locked = _locked_keys(actor.role, b.stage, pinned, answers, insp.answers)
    if locked:
        raise err("FIELD_ACCESS", "You cannot change these fields at this stage.", 403, keys=locked)
    merged = {k: {**(insp.answers.get(k) or {}), **(answers.get(k) or {})} for k in PARTS}
    new = _clean_all(b, pinned, merged, kept=insp.answers)
    changed = [(part, k) for part in PARTS
               for k in sorted(set(new[part]) | set(insp.answers.get(part) or {}))
               if new[part].get(k) != (insp.answers.get(part) or {}).get(k)]
    _check_files(actor, b, pinned, insp.answers, new, changed)
    keys = sorted(k for _, k in changed)
    if keys:
        insp.answers = new
        stamp(insp, actor, keys)
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
    check_fresh(insp, row_version, "STALE_INSPECTION", "inspection")
    try:
        scoring.validate_overrides(insp.form_version, body)
    except ValueError as e:
        raise err("INVALID_OVERRIDES", str(e)) from e
    # no review of work nobody has sent (F-238), nor Key Check texts while it is being inspected
    if insp.status != "submitted" or (body.get("key_checks") and insp.booking.stage not in (
            "submitted", "completed")):
        raise err("NOT_SUBMITTED", "Ratings and Key Checks can be set once the expert submits.",
                  409)
    before = {k: v["value"] for k, v in ((insp.scores or {}).get("key_checks") or {}).items()}
    insp.overrides = scoring.apply_overrides(insp.overrides, body)
    stamp(insp, actor, ["overrides"])
    insp.save()
    scoring.recompute(insp)
    if set(body) - {"key_checks"}:
        activity.log(insp.booking, actor, "ratings_changed", keys=[], inspection=insp)
    after = {k: v["value"] for k, v in insp.scores.get("key_checks", {}).items()}
    moved = {f"check.{k}": [before.get(k), after.get(k)] for k in body.get("key_checks") or {}
             if before.get(k) != after.get(k)}
    if moved:
        activity.log(insp.booking, actor, "key_checks_changed", moved, inspection=insp)
    events.emit("inspection.updated", booking=str(insp.booking_id), inspection=str(insp.id),
                keys=["overrides"])                       # the report is made again (handlers)
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
    core_tasks.after_commit(lambda: _after_resolving(b.id))
    return b


def _after_resolving(booking_id) -> None:
    """The kept inspection now counts: a booking waiting for it completes (its first report is
    made then); one already completed gets its report made again once, from the kept one."""
    from apps.media.services import check_completion
    from apps.reports.tasks import render_report

    if not check_completion(booking_id) and Booking.objects.filter(
            pk=booking_id, stage="completed").exists():
        render_report.delay(str(booking_id))
