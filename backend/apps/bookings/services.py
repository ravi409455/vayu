from datetime import date

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts import audit
from apps.accounts.models import Role, User
from apps.core import events
from apps.core.errors import CodedError
from apps.forms.access import levels_for
from apps.forms.fieldtypes import AnswerError, clean_answer
from apps.forms.models import Field, Form, FormKind, FormVersion, MasterListItem, VersionStatus
from apps.forms.rules import validate_answers

from .models import Booking, RescheduleLog
from .stages import can_transition

COLUMNS = {"customer_name": "customer_name", "customer_phone": "customer_phone", "city": "city",
           "car_make_model": "car_make_model", "inspection_type": "inspection_type",
           "booking_id": "booking_id"}
ACTION_ONLY = ("assigned_expert", "inspection_type")  # changed through their own actions


def err(code: str, message: str, status: int = 400, **extra) -> CodedError:
    return CodedError(code, message, status, **extra)


def today() -> str:
    return timezone.localdate().isoformat()


def booking_form_version() -> FormVersion:
    form = Form.objects.filter(kind=FormKind.BOOKING, is_active=True).first()
    version = (form.versions.filter(status=VersionStatus.PUBLISHED).order_by("-number").first()
               if form else None)
    if version is None:
        raise err("NO_BOOKING_FORM", "Publish the booking form first.", 409)
    return version


def active_item(list_key: str, key: str) -> bool:
    return MasterListItem.objects.filter(list__key=list_key, key=key, archived=False).exists()


def clean(version: FormVersion, answers: dict) -> dict:
    cleaned, errors = validate_answers(version, {"booking": answers}, today())
    if errors:
        raise err("INVALID_ANSWERS", "Some answers are invalid.", errors=errors)
    return cleaned


def sync_columns(b: Booking) -> None:
    a = b.answers
    for key, column in COLUMNS.items():
        setattr(b, column, a.get(key) or "")
    b.inspection_date = (date.fromisoformat(a["inspection_date"])
                         if a.get("inspection_date") else None)


def _ensure_unique(booking_id: str, exclude=None) -> None:
    qs = Booking.objects.filter(booking_id__iexact=booking_id.strip())
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    if qs.exists():
        raise err("DUPLICATE_BOOKING_ID", f"Booking ID '{booking_id}' is already used.")


def _save(b: Booking) -> None:
    try:
        with transaction.atomic():
            b.save()
    except IntegrityError as e:  # lost a race on the unique booking ID
        raise err("DUPLICATE_BOOKING_ID", "That booking ID is already used.") from e


def _touch(b: Booking, actor, keys: list[str]) -> None:
    b.row_version += 1
    b.last_edited_by, b.last_edited_at = actor, timezone.now()
    b.last_change = {"by": actor.username, "at": b.last_edited_at.isoformat(), "keys": keys}


def create(actor, answers: dict) -> Booking:
    version = booking_form_version()
    cleaned = clean(version, answers)
    _ensure_unique(cleaned["booking_id"])
    b = Booking(answers=cleaned, created_by=actor, last_edited_by=actor,
                last_edited_at=timezone.now())
    sync_columns(b)
    if cleaned.get("assigned_expert"):
        b.assigned_expert_id, b.stage = cleaned["assigned_expert"], "assigned"
    _save(b)
    events.emit("booking.created", booking=str(b.id), booking_id=b.booking_id)
    return b


@transaction.atomic
def edit(actor, b: Booking, new_answers: dict, row_version: int) -> Booking:
    b = Booking.objects.select_for_update().get(pk=b.pk)
    if row_version != b.row_version:
        raise err("STALE_BOOKING", "Someone changed this booking since you opened it.", 409,
                  changed_by=b.last_change.get("by"), changed_at=b.last_change.get("at"),
                  changed_keys=b.last_change.get("keys", []), row_version=b.row_version)
    forbidden = [k for k in new_answers if k in ACTION_ONLY]
    if forbidden:
        raise err("USE_ACTION", f"{', '.join(forbidden)} change through their own actions.")
    version = booking_form_version()
    levels = levels_for(version, actor.role, b.stage)
    default = "edit" if actor.role == "admin" else "view"
    # Hidden fields are refused whatever the value (else a 403-or-not leaks whether a guess
    # matches); read-only fields may be re-sent unchanged, as a UI resends the whole form.
    locked = sorted(k for k, v in new_answers.items()
                    if levels.get(k, default) == "hidden"
                    or (v != b.answers.get(k) and levels.get(k, default) != "edit"))
    if locked:  # checked before validation
        raise err("FIELD_ACCESS", "You cannot change these fields at this stage.", 403, keys=locked)
    merged = {**b.answers, **new_answers}
    cleaned = clean(version, merged)
    changes = {k: [b.answers.get(k), cleaned.get(k)] for k in set(cleaned) | set(b.answers)
               if b.answers.get(k) != cleaned.get(k)}
    if "booking_id" in changes:
        _ensure_unique(cleaned["booking_id"], exclude=b)
    if not changes:
        return b
    b.answers = cleaned
    sync_columns(b)
    _touch(b, actor, sorted(changes))
    _save(b)
    events.emit("booking.updated", booking=str(b.id), booking_id=b.booking_id, changes=changes)
    return b


def _lock(b: Booking) -> Booking:
    return Booking.objects.select_for_update().get(pk=b.pk)


def _changed(actor, b: Booking, changes: dict) -> None:
    _touch(b, actor, sorted(changes))
    _save(b)
    events.emit("booking.updated", booking=str(b.id), booking_id=b.booking_id, changes=changes)


@transaction.atomic
def assign(actor, b: Booking, expert_id) -> Booking:
    b = _lock(b)
    expert = User.objects.filter(pk=expert_id, role=Role.EXPERT, is_active=True).first()
    if expert is None:
        raise err("INVALID_EXPERT", "Choose an active expert.")
    if b.stage == "in_progress":
        raise err("ALREADY_STARTED", "The expert has started; force-release the job first.", 409)
    if not can_transition(b.stage, "assigned"):
        raise err("INVALID_STAGE", f"A {b.stage} booking cannot be assigned.", 409)
    changes = {"stage": [b.stage, "assigned"], "assigned_expert": [b.assigned_expert_id, expert.id]}
    b.stage, b.assigned_expert = "assigned", expert
    b.answers = {**b.answers, "assigned_expert": expert.id}
    _changed(actor, b, changes)
    events.emit("booking.assigned", booking=str(b.id), booking_id=b.booking_id, expert=expert.id)
    return b


@transaction.atomic
def reschedule(actor, b: Booking, date_, time_, reason) -> Booking:
    b = _lock(b)
    if b.stage not in ("draft", "assigned"):
        raise err("INVALID_STAGE", f"A {b.stage} booking cannot be rescheduled.", 409)
    if not isinstance(reason, str) or not active_item("reschedule_reason", reason):
        raise err("INVALID_REASON", "Choose a reschedule reason from the list.")
    try:
        d = clean_answer(Field(type="date", config={}), date_)
        t = clean_answer(Field(type="time", config={}), time_)
    except AnswerError as e:
        raise err("INVALID_SCHEDULE", str(e)) from e
    RescheduleLog.objects.create(booking=b, old_date=b.answers["inspection_date"],
                                 old_time=b.answers["inspection_time"], new_date=d, new_time=t,
                                 reason=reason, by=actor)
    changes = {"inspection_date": [b.answers["inspection_date"], d],
               "inspection_time": [b.answers["inspection_time"], t]}
    b.answers = {**b.answers, "inspection_date": d, "inspection_time": t}
    sync_columns(b)
    _changed(actor, b, changes)
    return b


@transaction.atomic
def cancel(actor, b: Booking, reason) -> Booking:
    b = _lock(b)
    if not isinstance(reason, str) or not active_item("cancel_reason", reason):
        raise err("INVALID_REASON", "Choose a cancel reason from the list.")
    if not can_transition(b.stage, "cancelled"):
        raise err("INVALID_STAGE", f"A {b.stage} booking cannot be cancelled.", 409)
    changes = {"stage": [b.stage, "cancelled"]}
    b.stage, b.cancel_reason, b.cancelled_at = "cancelled", reason, timezone.now()
    _changed(actor, b, changes)
    return b


@transaction.atomic
def force_release(actor, b: Booking) -> Booking:
    b = _lock(b)
    if b.stage != "in_progress":
        raise err("NOT_STARTED", "Only a started job can be force-released.", 409)
    b.stage, b.started_at = "assigned", None
    b.released_by, b.released_at, b.released_draft_expected = actor, timezone.now(), True
    audit.record(actor, "booking.force_release", "booking", b.id,
                 f"Force-released {b.booking_id} from expert {b.assigned_expert_id}")
    _changed(actor, b, {"stage": ["in_progress", "assigned"]})
    return b


@transaction.atomic
def change_type(actor, b: Booking, inspection_type) -> Booking:
    b = _lock(b)
    if b.started_at is not None or b.stage not in ("draft", "assigned"):
        raise err("TYPE_LOCKED", "The inspection type is locked once the job has started.", 409)
    if not isinstance(inspection_type, str) or not active_item("inspection_type", inspection_type):
        raise err("INVALID_TYPE", "Choose an inspection type from the list.")
    changes = {"inspection_type": [b.inspection_type, inspection_type]}
    b.answers = {**b.answers, "inspection_type": inspection_type}
    sync_columns(b)
    _changed(actor, b, changes)
    return b


def delete(actor, b: Booking) -> None:
    audit.record(actor, "booking.delete", "booking", b.id, f"Deleted booking {b.booking_id}")
    events.emit("booking.deleted", booking=str(b.id), booking_id=b.booking_id)
    b.delete()
