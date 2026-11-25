import logging
from unittest import mock

import pytest
from django.db import OperationalError

from apps.core.views import workers_alive as REAL_WORKERS_ALIVE

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _up():
    """The file store and a worker answer, unless a test says otherwise."""
    with mock.patch("apps.media.storage.client"), \
            mock.patch("apps.core.views.workers_alive", return_value=True):
        yield


def test_health_ok(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_503_when_db_down(client):
    with mock.patch("apps.core.views.connection") as conn:
        conn.cursor.side_effect = OperationalError("down")
        r = client.get("/api/v1/health")
    assert r.status_code == 503
    assert r.json() == {"status": "degraded"}  # no dependency detail leaked


def test_health_503_when_redis_down(client):
    with mock.patch("apps.core.views.redis_client") as rc:
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
    with caplog.at_level(logging.INFO, logger="apps.core.views"):
        client.get("/api/v1/health", headers={"X-Request-ID": "rid-9"})
    assert any(getattr(rec, "request_id", None) == "rid-9" for rec in caplog.records)


def test_request_id_from_client_is_sanitised(client):
    r = client.get("/api/v1/health", headers={"X-Request-ID": "bad id\twith spaces"})
    assert r["X-Request-ID"] != "bad id\twith spaces" and len(r["X-Request-ID"]) == 32


def test_health_503_when_the_file_store_or_the_workers_are_down(client):
    """F-210: the API answering is not enough."""
    with mock.patch("apps.media.storage.client") as c:
        c.return_value.head_bucket.side_effect = OSError("R2 down")
        assert client.get("/api/v1/health").status_code == 503
    with mock.patch("apps.core.views.workers_alive", return_value=False):
        assert client.get("/api/v1/health").status_code == 503


def test_workers_alive_asks_celery_and_never_raises():
    real = REAL_WORKERS_ALIVE
    with mock.patch("vayu.celery.app.control.ping", return_value=[{"w@h": {"ok": "pong"}}]):
        assert real() is True
    with mock.patch("vayu.celery.app.control.ping", side_effect=OSError("no broker")):
        assert real() is False
