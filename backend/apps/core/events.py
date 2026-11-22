"""Domain events (booking.created, ...). Phase 9 delivers them to webhooks; until then they can
be observed with `capture()` (tests) or `subscribe()`."""
from collections.abc import Callable
from contextlib import contextmanager

_subscribers: list[Callable[[str, dict], None]] = []


def subscribe(fn: Callable[[str, dict], None]) -> None:
    _subscribers.append(fn)


def emit(name: str, **payload) -> None:
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
