import logging
from unittest import mock

import pytest
from django.db import OperationalError

pytestmark = pytest.mark.django_db


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
