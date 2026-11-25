"""Shared pytest fixtures, imported by the root conftest.py."""
import logging
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User

PASSWORD = "Str0ng-pass-1"  # noqa: S105 - test-only password


@pytest.fixture
def make_user(db: Any) -> Any:
    counter = iter(range(1, 10_000))

    def _make(role: Any=Role.EXPERT, username: Any=None, password: Any=PASSWORD, **kw: Any) -> Any:
        username = username or f"{role}{next(counter)}"
        kw.setdefault("name", username.title())
        kw.setdefault("must_change_password", False)
        return User.objects.create_user(username=username, password=password, role=role, **kw)

    return _make


@pytest.fixture
def login() -> Any:
    def _login(client: Any, username: Any, password: Any = PASSWORD, **extra: Any) -> Any:
        body = {"username": username, "password": password, "client": "mobile", **extra}
        return client.post("/api/v1/auth/login", body, format="json")

    return _login


@pytest.fixture
def api_as(make_user: Any) -> Any:
    """Client force-authenticated as a fresh user of the given role (skips token checks)."""

    def _as(role: Any) -> Any:
        user = make_user(role)
        client = APIClient()
        client.force_authenticate(user=user)
        return client, user

    return _as


_PLAIN = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


@pytest.fixture
def logged(caplog: Any) -> Any:
    """The structured events (apps.core.log) logged so far: logged("pdf.render_done") is a list
    of each one's fields; logged() all of them as (name, fields)."""
    caplog.set_level(logging.INFO, logger="vayu.events")

    def _get(name: str | None = None) -> Any:
        rows = [(r.event, {k: v for k, v in vars(r).items() if k not in _PLAIN})
                for r in caplog.records if r.name == "vayu.events"]
        return [f for n, f in rows if n == name] if name else rows

    return _get
