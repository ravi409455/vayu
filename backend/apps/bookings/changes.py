"""Who changed a booking or an inspection, and the guard against saving over someone else's change
(F-006): one stamp and one "stale" answer, used by every path that edits them."""
from django.utils import timezone

from apps.core.errors import CodedError


def stamp(obj, actor, keys: list[str], *, edited: bool = True) -> None:
    """One change to a booking or inspection: its version goes up, and who (None: the system),
    when and which keys are kept. [edited]: also the "last edited by" columns."""
    now = timezone.now()
    obj.row_version += 1
    if edited and actor is not None:
        obj.last_edited_by, obj.last_edited_at = actor, now
    obj.last_change = {"by": actor.shown_name if actor is not None else "system",
                       "at": now.isoformat(), "keys": keys}


def check_fresh(obj, row_version, code: str, what: str) -> None:
    """Refuse a save made from an old copy, saying who changed it, when and what."""
    if row_version != obj.row_version:
        raise CodedError(code, f"Someone changed this {what} since you opened it.", 409,
                         changed_by=obj.last_change.get("by"),
                         changed_at=obj.last_change.get("at"),
                         changed_keys=obj.last_change.get("keys", []),
                         row_version=obj.row_version)
