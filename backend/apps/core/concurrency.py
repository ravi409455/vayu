"""The one guard against saving over someone else's change (Q2.2): every editor sends the version
it started from, and a save made from an old copy is refused with 409 and the current version."""
from typing import Any

from .errors import fail


def check_row_version(obj: Any, sent: Any, code: str, message: str, *,
                      field: str = "row_version", who: bool = False) -> None:
    """Refuse the save when [sent] is not [obj]'s current [field]. The error carries the current
    value under [field]; [who]: also who changed it, when and which keys (from obj.last_change).

    `check_row_version(booking, 3, "STALE_BOOKING", "Someone changed this booking…", who=True)`"""
    current = getattr(obj, field)
    if sent == current:
        return
    extra: dict[str, Any] = {}
    if who:
        extra = {"changed_by": obj.last_change.get("by"), "changed_at": obj.last_change.get("at"),
                 "changed_keys": obj.last_change.get("keys", [])}
    raise fail(code, message, 409, **extra, **{field: current})
