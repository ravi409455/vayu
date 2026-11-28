"""Domain events (booking.created, ...). Webhooks (integrations), the report (reports) and the bell
and pushes (notify) subscribe in their apps' ready(); tests watch them with `capture()`."""
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any

_subscribers: list[Callable[[str, dict[str, Any]], None]] = []

# every event there is (F-044): an emit of anything else is a typo and raises
NAMES = frozenset({
    "booking.created", "booking.updated", "booking.assigned", "booking.deleted",
    "inspection.started", "checkin.completed", "inspection.submitted", "inspection.updated",
    "inspection.completed",
    "media.completed", "media.deleted", "pdf.ready",
    "alert.conflict", "alert.late_work", "alert.pdf_failed", "alert.stuck_upload",
    "alert.type_change_rejected",
})


def subscribe(fn: Callable[[str, dict[str, Any]], None]) -> None:
    _subscribers.append(fn)


def emit(name: str, **payload: Any) -> None:
    if name not in NAMES:
        raise ValueError(f"Unknown event {name!r}: add it to apps.core.events.NAMES.")
    for fn in list(_subscribers):
        fn(name, payload)


@contextmanager
def capture() -> Any:
    seen: list[tuple[str, dict[str, Any]]] = []
    fn = lambda name, payload: seen.append((name, payload))  # noqa: E731
    _subscribers.append(fn)
    try:
        yield seen
    finally:
        _subscribers.remove(fn)
