from unittest import mock

import requests

from apps.platform.tasks import heartbeat


def test_heartbeat_pings_when_set_and_never_raises(settings):
    settings.WORKERS_HEARTBEAT_URL = ""
    with mock.patch("apps.platform.tasks.requests.get") as get:
        heartbeat()
        get.assert_not_called()
    settings.WORKERS_HEARTBEAT_URL = "https://uptime.example/hb"
    with mock.patch("apps.platform.tasks.requests.get") as get:
        heartbeat()
        get.assert_called_once_with("https://uptime.example/hb", timeout=10)
    with mock.patch("apps.platform.tasks.requests.get", side_effect=requests.ConnectionError):
        heartbeat()   # a failed ping only logs


def test_heartbeat_is_scheduled(settings):
    assert settings.CELERY_BEAT_SCHEDULE["heartbeat"]["task"] == "apps.platform.tasks.heartbeat"
