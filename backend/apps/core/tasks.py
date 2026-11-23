"""Run work only once the surrounding database transaction has committed. A worker that starts
earlier would read data that is not saved yet (and silently find nothing to do)."""
from collections.abc import Callable

from django.db import transaction


def after_commit(fn: Callable[[], object]) -> None:
    transaction.on_commit(fn)
