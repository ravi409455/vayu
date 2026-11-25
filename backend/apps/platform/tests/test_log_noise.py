"""F-231: the logs keep what matters (health probes only when unhealthy, no PDF chatter)."""
import io
import logging
from typing import cast
from unittest import mock

import pytest
from django.conf import settings
from django.core.management import call_command

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _up():
    with mock.patch("apps.media.storage.client"), \
            mock.patch("apps.platform.views.workers_alive", return_value=True):
        yield


def test_a_healthy_probe_logs_nothing_and_a_failed_one_warns(client, caplog):
    with caplog.at_level(logging.INFO, logger="apps.platform.views"):
        client.get("/api/v1/health")
    assert not [r for r in caplog.records if r.name == "apps.platform.views"]
    with caplog.at_level(logging.INFO, logger="apps.platform.views"), \
            mock.patch("apps.platform.views.redis_client") as rc:
        rc.return_value.ping.side_effect = ConnectionError("down")
        client.get("/api/v1/health")
    [rec] = [r for r in caplog.records if r.name == "apps.platform.views"]
    assert rec.levelno == logging.WARNING and rec.redis == "down"


def test_pdf_progress_lines_and_schema_type_warnings_stay_out_of_the_logs():
    loggers = cast(dict, settings.LOGGING)["loggers"]
    assert loggers["weasyprint.progress"]["level"] == "WARNING"
    out, err = io.StringIO(), io.StringIO()
    call_command("check", "--deploy", stdout=out, stderr=err)      # ~70 W002 lines without it
    assert "W002" not in out.getvalue() + err.getvalue()
