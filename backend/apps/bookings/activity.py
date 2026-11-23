"""The booking timeline: one row per thing that happened (see BookingActivity)."""
from apps.forms.access import levels_for

from .models import BookingActivity

# values worth keeping for the timeline (still shown only to people who may see the field)
SAFE_KEYS = {"stage", "assigned_expert", "inspection_date", "inspection_time", "inspection_type",
             "conflict"}
COLUMNS = {"stage", "conflict"}       # booking columns, not form answers: always visible


def log(b, actor, kind: str, changes: dict | None = None, keys: list[str] | None = None,
        inspection=None) -> None:
    changes = changes or {}
    BookingActivity.objects.create(
        booking=b, actor=actor if getattr(actor, "pk", None) else None, kind=kind,
        changes={k: v for k, v in changes.items() if k in SAFE_KEYS},
        keys=sorted(keys if keys is not None else changes), inspection=inspection)


def for_user(b, user) -> list[dict]:
    """The timeline as this person may see it. Fail closed: a key (and its value) is shown only
    when the person may see that field at the booking's current stage; rows about an inspection
    form whose submissions they may not see are left out."""
    from apps.forms.access import hidden_inspection_forms

    from .services import booking_form_version

    role = user.role
    admin = role == "admin"
    booking_levels = {} if admin else levels_for(booking_form_version(), role, b.stage)
    hidden_forms = set() if admin else set(hidden_inspection_forms(user))
    insp_levels: dict = {}

    def shown(row, key: str) -> bool:
        if admin or key in COLUMNS:
            return True
        if row.inspection_id is None:
            return booking_levels.get(key, "hidden") != "hidden"
        part, _, field = key.partition(".")
        cache_key = (row.inspection_id, part)
        if cache_key not in insp_levels:
            version = row.inspection.pinned().get(part)
            insp_levels[cache_key] = levels_for(version, role, b.stage) if version else {}
        return insp_levels[cache_key].get(field, "hidden") != "hidden"

    rows = b.activity.select_related("actor", "inspection__form_version",
                                     "inspection__start_version", "inspection__end_version")
    out = []
    for row in rows[:200]:
        if row.inspection_id and row.inspection.form_version.form_id in hidden_forms:
            continue
        out.append({
            "at": row.at.isoformat(), "kind": row.kind,
            "by": None if row.actor is None else {"id": row.actor.pk, "role": row.actor.role,
                                                  "name": row.actor.name or row.actor.username},
            "changes": {k: v for k, v in row.changes.items() if shown(row, k)},
            "keys": [k for k in row.keys if shown(row, k)],
        })
    return out
