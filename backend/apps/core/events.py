"""Domain events (booking.created, ...). Phase 9 delivers them to webhooks; until then they can
be observed with `capture()` (tests) or `subscribe()`."""
from collections.abc import Callable
from contextlib import contextmanager

_subscribers: list[Callable[[str, dict], None]] = []

# every event there is (F-044): an emit of anything else is a typo and raises
NAMES = frozenset({
    "booking.created", "booking.updated", "booking.assigned", "booking.deleted",
    "inspection.started", "inspection.submitted", "inspection.updated", "inspection.completed",
    "media.completed", "media.deleted", "pdf.ready",
    "alert.conflict", "alert.late_work", "alert.pdf_failed", "alert.stuck_upload",
    "alert.type_change_rejected",
})


def subscribe(fn: Callable[[str, dict], None]) -> None:
    _subscribers.append(fn)


def emit(name: str, **payload) -> None:
    if name not in NAMES:
        raise ValueError(f"Unknown event {name!r}: add it to apps.core.events.NAMES.")
    for fn in list(_subscribers):
        fn(name, payload)


@contextmanager
def capture():
    seen: list[tuple[str, dict]] = []
    fn = lambda name, payload: seen.append((name, payload))  # noqa: E731
    _subscribers.append(fn)
    try:
        yield seen
    finally:
        _subscribers.remove(fn)
