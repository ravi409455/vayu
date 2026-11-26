"""Health (database, Redis, storage, workers) and the Settings page's API: they need media and
accounts, so they live above core (F-003)."""
import json
import logging

import redis
from django.conf import settings
from django.db import connection
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import audit
from apps.accounts.permissions import perm
from apps.core import app_settings


class SettingView(APIView):
    """GET / PUT one settings group ("timing", "media"). Ops may read, only Admin may change."""

    permission_classes = [perm("settings.view", "settings.edit")]
    declared_permissions = ("settings.view", "settings.edit")

    def get(self, request, key):
        return Response(app_settings.get(self._key(key)))

    def put(self, request, key):
        old, new = app_settings.put(self._key(key), request.data)
        audit.record(request.user, f"settings.{key}", "setting", key,
                     f"Changed {key} settings: {json.dumps(old)} -> {json.dumps(new)}")
        return Response(new)

    @staticmethod
    def _key(key: str) -> str:
        if key not in app_settings.DEFAULTS:
            raise NotFound()
        return key


logger = logging.getLogger(__name__)


def redis_client() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)


def workers_alive() -> bool:
    """Does at least one Celery worker answer within a second?"""
    from vayu.celery import app

    try:
        return bool(app.control.ping(timeout=1.0))
    except Exception:  # noqa: BLE001
        return False


SLOW_CHECKS_FOR = 30      # seconds: anyone may call /health, the storage and worker pings cost


def slow_checks() -> dict:
    """The file store, the background workers and the push credential (F-210, H-3): a dead one
    stops uploads, reports, webhooks or pushes while the API still answers. Kept for a while, so
    a busy caller never ties up a web worker for the worker ping's full second."""
    from django.core.cache import cache

    found = cache.get("health:slow")
    if found is not None:
        return found
    found = {}
    try:
        from apps.media import storage

        storage.client().head_bucket(Bucket=settings.S3_BUCKET)
        found["storage"] = "ok"
    except Exception:  # noqa: BLE001
        found["storage"] = "down"
    found["workers"] = "ok" if workers_alive() else "down"
    if settings.FCM_CREDENTIALS:          # set but missing: every push fails
        from pathlib import Path

        found["push"] = "ok" if Path(settings.FCM_CREDENTIALS).is_file() else "down"
    cache.set("health:slow", found, SLOW_CHECKS_FOR)
    return found


class HealthView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, request):
        status = {"db": "ok", "redis": "ok"}
        try:
            with connection.cursor() as cur:
                cur.execute("SELECT 1")
        except Exception:  # noqa: BLE001 - any failure means unhealthy
            status["db"] = "down"
        try:
            redis_client().ping()
        except Exception:  # noqa: BLE001
            status["redis"] = "down"
        status.update(slow_checks())
        healthy = all(v == "ok" for v in status.values())
        # Dependency detail goes to the logs only, and only when something is down (a probe every
        # few seconds would otherwise fill the logs, F-231); the public body stays bare.
        if not healthy:
            logger.warning("health check failed", extra={"healthy": healthy, **status})
        return Response({"status": "ok" if healthy else "degraded"},
                        status=200 if healthy else 503)
