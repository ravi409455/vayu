import pytest

from apps.core import tasks as core_tasks
from apps.core.testing import api_as, login, make_user  # noqa: F401  (pytest fixtures)


def pytest_configure(config):
    config.addinivalue_line("markers", "real_commit: keep transaction.on_commit deferral")


@pytest.fixture(autouse=True)
def _run_after_commit_at_once(request, monkeypatch):
    """Tests run inside one open transaction, so on_commit callbacks would never fire. Run them
    at once, except in tests that check the deferral itself (marker real_commit)."""
    if request.node.get_closest_marker("real_commit") is None:
        monkeypatch.setattr(core_tasks, "after_commit", lambda fn: fn())


@pytest.fixture(autouse=True)
def _fresh_cache():
    from django.core.cache import cache

    cache.clear()
