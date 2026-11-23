"""The booking timeline: one row per thing that happened (see BookingActivity)."""
from apps.forms.access import levels_for

from .models import BookingActivity

# values safe to show to anyone who can see the booking (they are on the booking list anyway)
SAFE_KEYS = {"stage", "assigned_expert", "inspection_date", "inspection_time", "inspection_type",
             "conflict"}


def log(b, actor, kind: str, changes: dict | None = None, keys: list[str] | None = None,
        inspection=None) -> None:
    changes = changes or {}
    BookingActivity.objects.create(
        booking=b, actor=actor if getattr(actor, "pk", None) else None, kind=kind,
        changes={k: v for k, v in changes.items() if k in SAFE_KEYS},
        keys=sorted(keys if keys is not None else changes), inspection=inspection)


def for_user(b, user) -> list[dict]:
    """The timeline as this person may see it: keys of fields hidden from them are left out."""
    from .services import booking_form_version

    role = user.role
    booking_levels = {} if role == "admin" else levels_for(booking_form_version(), role, b.stage)
    insp_levels: dict = {}

    def shown(row, key: str) -> bool:
        if role == "admin" or key in SAFE_KEYS:
            return True
        if row.inspection_id is None:
            return booking_levels.get(key, "view") != "hidden"
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
        out.append({
            "at": row.at.isoformat(), "kind": row.kind,
            "by": None if row.actor is None else {"id": row.actor.pk, "role": row.actor.role,
                                                  "name": row.actor.name or row.actor.username},
            "changes": row.changes, "keys": [k for k in row.keys if shown(row, k)],
        })
    return out
