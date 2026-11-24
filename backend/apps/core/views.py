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

from . import app_settings

logger = logging.getLogger(__name__)


def redis_client() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)


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
        healthy = all(v == "ok" for v in status.values())
        # Dependency detail goes to the logs only; the public body stays bare.
        logger.info("health check", extra={"healthy": healthy, **status})
        return Response({"status": "ok" if healthy else "degraded"},
                        status=200 if healthy else 503)


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
