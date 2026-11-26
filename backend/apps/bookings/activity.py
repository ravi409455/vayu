"""The booking timeline: one row per thing that happened (see BookingActivity)."""
import json
import uuid

from apps.forms.access import levels_for

from .models import BookingActivity

# kept as they are (the screens read them); every other changed value is kept short by _short and,
# like these, shown only to people who may see that field
SAFE_KEYS = {"alert", "stage", "assigned_expert", "inspection_date", "inspection_time",
             "inspection_type", "conflict", "media", "revision", "how", "missing"}
# not form answers: always visible ("missing": how many files a job was finished without)
COLUMNS = {"alert", "stage", "conflict", "revision", "how", "missing"}
TIMING_KINDS = ("late_reviewed", "quick_reviewed")   # Admin / Ops only, never Experts
REPORT_KINDS = ("report_downloaded", "report_shared")   # who passed the report on: not Experts
# Ops' review of an inspection: experts never see or set ratings (REQUIREMENTS §5.4, F-237)
REVIEW_KINDS = ("ratings_changed", "key_checks_changed", "alert_cleared")


MAX_TEXT = 200   # a long note keeps its first 200 characters in the timeline


def _is_file_id(v) -> bool:
    # ponytail: answers hold uploaded files as their uuid; a text answer that is exactly a uuid
    # would read as "1 file" (none of our forms ask for one)
    try:
        return isinstance(v, str) and len(v) == 36 and bool(uuid.UUID(v))
    except ValueError:
        return False


def _short(v):
    """A changed value as the timeline keeps it: files counted (not their ids), long text cut."""
    if _is_file_id(v):
        return "1 file"
    if isinstance(v, list) and v and all(_is_file_id(x) for x in v):
        return f"{len(v)} file{'' if len(v) == 1 else 's'}"
    if isinstance(v, (list, dict)):
        text = json.dumps(v, ensure_ascii=False, default=str)
        return v if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "…"
    if isinstance(v, str) and len(v) > MAX_TEXT:
        return v[:MAX_TEXT] + "…"
    return v


def _kept(k: str, v):
    if _plain(k):
        return v
    if isinstance(v, (list, tuple)) and len(v) == 2:
        return [_short(v[0]), _short(v[1])]
    return _short(v)


def log(b, actor, kind: str, changes: dict | None = None, keys: list[str] | None = None,
        inspection=None) -> None:
    changes = changes or {}
    BookingActivity.objects.create(
        booking=b, booking_ref=b.booking_id,
        actor=actor if getattr(actor, "pk", None) else None, kind=kind,
        changes={k: _kept(k, v) for k, v in changes.items()},
        keys=sorted(keys if keys is not None else changes), inspection=inspection)


def forget_values(b) -> None:
    """A deleted booking's rows stay for metrics (F-247) but keep no customer answers: only the
    schedule / stage / assignment values, which say nothing about the customer."""
    rows = list(BookingActivity.objects.filter(booking=b))
    for row in rows:
        row.changes = {k: v for k, v in row.changes.items() if _plain(k)}
    BookingActivity.objects.bulk_update(rows, ["changes"])


def for_user(b, user, since=None, values: bool = True) -> list[dict]:
    """The timeline as this person may see it. Fail closed: a key (and its value) is shown only
    when the person may see that field at the booking's current stage; rows about an inspection
    form whose submissions they may not see are left out. ``since``: only what others did after it
    (the phone's "what Ops changed" banner). ``values=False``: only the SAFE_KEYS values, as
    before every value was kept: the phone's screens stay as they were; only the web shows the
    old and new value of every change."""
    return for_bookings([b], user, since, values)[b.id]


def _plain(k: str) -> bool:
    return k in SAFE_KEYS or k.startswith("check.")


def for_bookings(bookings, user, since=None, values: bool = True) -> dict:
    """for_user of many bookings at once, in a fixed number of queries (the phone's sync, H-12)."""
    from apps.accounts.permissions import scope_for
    from apps.forms.access import hidden_inspection_forms

    from .models import BookingActivity
    from .services import booking_form_version

    role = user.role
    admin = role == "admin"
    booking_version = None if admin else booking_form_version()
    hidden_forms = set() if admin else set(hidden_inspection_forms(user))
    levels: dict = {}

    def level(version, stage, key) -> str:
        if (version.id, stage) not in levels:
            levels[(version.id, stage)] = levels_for(version, role, stage)
        return levels[(version.id, stage)].get(key, "hidden")

    def shown(b, row, key: str) -> bool:
        if admin or key in COLUMNS:
            return True
        if key.startswith("check."):          # a Key Check: Ops' review, never for experts
            return role != "expert"
        if row.inspection_id is None:
            return level(booking_version, b.stage, key) != "hidden"
        part, _, field = key.partition(".")
        version = row.inspection.pinned().get(part)
        return version is not None and level(version, b.stage, field) != "hidden"

    rows = BookingActivity.objects.filter(booking__in=bookings).select_related(
        "actor", "inspection__form_version", "inspection__start_version",
        "inspection__end_version")
    if scope_for(user, "bookings.review_timing") is None:
        rows = rows.exclude(kind__in=TIMING_KINDS)
    if role == "expert":
        rows = rows.exclude(kind__in=REPORT_KINDS + REVIEW_KINDS)
    if since is not None:
        rows = rows.filter(at__gt=since).exclude(actor=user)
    by_booking: dict = {}
    for row in rows:
        by_booking.setdefault(row.booking_id, []).append(row)
    out: dict = {}
    for b in bookings:
        out[b.id] = [{
            "at": row.at.isoformat(), "kind": row.kind,
            "by": None if row.actor is None else {"id": row.actor.pk, "role": row.actor.role,
                                                  "name": row.actor.name or row.actor.username},
            "changes": {k: v for k, v in row.changes.items()
                        if shown(b, row, k) and (values or _plain(k))},
            "keys": [k for k in row.keys if shown(b, row, k)],
        } for row in by_booking.get(b.id, [])[:200]
            if not (row.inspection_id and row.inspection.form_version.form_id in hidden_forms)]
    return out
