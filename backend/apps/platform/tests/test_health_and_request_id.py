import logging
from unittest import mock

import pytest
from django.db import OperationalError

from apps.platform.views import workers_alive as REAL_WORKERS_ALIVE

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _up():
    """The file store and a worker answer, unless a test says otherwise."""
    from django.core.cache import cache

    cache.delete("health:slow")
    with mock.patch("apps.media.storage.client"), \
            mock.patch("apps.platform.views.workers_alive", return_value=True):
        yield


def test_health_ok(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_503_when_db_down(client):
    with mock.patch("apps.platform.views.connection") as conn:
        conn.cursor.side_effect = OperationalError("down")
        r = client.get("/api/v1/health")
    assert r.status_code == 503
    assert r.json() == {"status": "degraded"}  # no dependency detail leaked


def test_health_503_when_redis_down(client):
    with mock.patch("apps.platform.views.redis_client") as rc:
        rc.return_value.ping.side_effect = ConnectionError("down")
        r = client.get("/api/v1/health")
    assert r.status_code == 503
    assert r.json() == {"status": "degraded"}


def test_request_id_generated_and_echoed(client):
    r = client.get("/api/v1/health")
    assert len(r["X-Request-ID"]) >= 16


def test_request_id_from_client_is_kept(client):
    r = client.get("/api/v1/health", headers={"X-Request-ID": "abc-123"})
    assert r["X-Request-ID"] == "abc-123"


def test_request_id_in_log_records(client, caplog):
    with caplog.at_level(logging.INFO, logger="apps.platform.views"), \
            mock.patch("apps.platform.views.redis_client") as rc:      # only a failed probe logs
        rc.return_value.ping.side_effect = ConnectionError("down")
        client.get("/api/v1/health", headers={"X-Request-ID": "rid-9"})
    assert any(getattr(rec, "request_id", None) == "rid-9" for rec in caplog.records)


def test_request_id_from_client_is_sanitised(client):
    r = client.get("/api/v1/health", headers={"X-Request-ID": "bad id\twith spaces"})
    assert r["X-Request-ID"] != "bad id\twith spaces" and len(r["X-Request-ID"]) == 32


def test_health_503_when_the_file_store_or_the_workers_are_down(client):
    """F-210: the API answering is not enough."""
    from django.core.cache import cache

    with mock.patch("apps.media.storage.client") as c:
        c.return_value.head_bucket.side_effect = OSError("R2 down")
        assert client.get("/api/v1/health").status_code == 503
    cache.delete("health:slow")
    with mock.patch("apps.platform.views.workers_alive", return_value=False):
        assert client.get("/api/v1/health").status_code == 503


def test_the_slow_checks_are_kept_for_a_while(client):
    """Anyone may call /health: the storage and worker pings run at most every 30 s."""
    with mock.patch("apps.platform.views.workers_alive", return_value=True) as ping:
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/api/v1/health").status_code == 200
    assert ping.call_count == 1


def test_a_push_credential_that_is_set_but_missing_is_reported(client, settings, tmp_path):
    settings.FCM_CREDENTIALS = str(tmp_path / "missing.json")
    assert client.get("/api/v1/health").status_code == 503
    from django.core.cache import cache

    cache.delete("health:slow")
    (tmp_path / "missing.json").write_text("{}")
    assert client.get("/api/v1/health").status_code == 200


def test_workers_alive_asks_celery_and_never_raises():
    real = REAL_WORKERS_ALIVE
    with mock.patch("vayu.celery.app.control.ping", return_value=[{"w@h": {"ok": "pong"}}]):
        assert real() is True
    with mock.patch("vayu.celery.app.control.ping", side_effect=OSError("no broker")):
        assert real() is False


def test_the_error_code_table_lists_every_code():
    """F-160: docs/error-codes.md is complete (regenerate it when this fails)."""
    from pathlib import Path

    from apps.platform.error_codes import codes, table

    doc = (Path(__file__).resolve().parents[4] / "docs" / "error-codes.md").read_text()
    assert table() in doc
    for code in ("ALREADY_SUBMITTED", "FORM_VERSION_OLD", "INVALID_VERSION", "LINK_EXPIRED",
                 "NOT_FOUND", "INVALID", "CANNOT_REGENERATE"):
        assert code in codes()
