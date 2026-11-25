"""Who changed a booking or an inspection (F-006): one stamp, used by every path that edits them.
The matching "stale" answer is apps.core.concurrency.check_row_version."""
from django.utils import timezone


def stamp(obj, actor, keys: list[str], *, edited: bool = True) -> None:
    """One change to a booking or inspection: its version goes up, and who (None: the system),
    when and which keys are kept. [edited]: also the "last edited by" columns."""
    now = timezone.now()
    obj.row_version += 1
    if edited and actor is not None:
        obj.last_edited_by, obj.last_edited_at = actor, now
    obj.last_change = {"by": actor.shown_name if actor is not None else "system",
                       "at": now.isoformat(), "keys": keys}

