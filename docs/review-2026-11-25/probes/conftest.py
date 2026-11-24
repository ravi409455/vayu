import pytest
from apps.core import tasks as core_tasks
from apps.core.testing import api_as, login, make_user  # noqa


@pytest.fixture(autouse=True)
def _now(monkeypatch):
    monkeypatch.setattr(core_tasks, "after_commit", lambda fn: fn())


@pytest.fixture(autouse=True)
def _fresh_cache():
    from django.core.cache import cache
    cache.clear()
