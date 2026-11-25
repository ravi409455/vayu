"""The booking timeline: one row per thing that happened (see BookingActivity)."""
from apps.forms.access import levels_for

from .models import BookingActivity

# values worth keeping for the timeline (still shown only to people who may see the field)
SAFE_KEYS = {"alert", "stage", "assigned_expert", "inspection_date", "inspection_time",
             "inspection_type", "conflict", "media", "revision", "how", "missing"}
# not form answers: always visible ("missing": how many files a job was finished without)
COLUMNS = {"alert", "stage", "conflict", "revision", "how", "missing"}
TIMING_KINDS = ("late_reviewed", "quick_reviewed")   # Admin / Ops only, never Experts
REPORT_KINDS = ("report_downloaded", "report_shared")   # who passed the report on: not Experts
# Ops' review of an inspection: experts never see or set ratings (REQUIREMENTS §5.4, F-237)
REVIEW_KINDS = ("ratings_changed", "key_checks_changed", "alert_cleared")


def log(b, actor, kind: str, changes: dict | None = None, keys: list[str] | None = None,
        inspection=None) -> None:
    changes = changes or {}
    BookingActivity.objects.create(
        booking=b, actor=actor if getattr(actor, "pk", None) else None, kind=kind,
        changes={k: v for k, v in changes.items() if k in SAFE_KEYS or k.startswith("check.")},
        keys=sorted(keys if keys is not None else changes), inspection=inspection)


def for_user(b, user, since=None) -> list[dict]:
    """The timeline as this person may see it. Fail closed: a key (and its value) is shown only
    when the person may see that field at the booking's current stage; rows about an inspection
    form whose submissions they may not see are left out. ``since``: only what others did after it
    (the phone's "what Ops changed" banner)."""
    return for_bookings([b], user, since)[b.id]


def for_bookings(bookings, user, since=None) -> dict:
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
            "changes": {k: v for k, v in row.changes.items() if shown(b, row, k)},
            "keys": [k for k in row.keys if shown(b, row, k)],
        } for row in by_booking.get(b.id, [])[:200]
            if not (row.inspection_id and row.inspection.form_version.form_id in hidden_forms)]
    return out
