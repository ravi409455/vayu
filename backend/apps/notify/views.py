from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Device
from apps.core.errors import CodedError

from .models import Notification

LIMIT = 50


def _device_id(request):
    return request.auth.get("device_id") if hasattr(request.auth, "get") else None


class PushTokenView(APIView):
    """The phone's Firebase token. A token moves with the phone, so it leaves any other device."""

    allow_password_change_pending = True

    def post(self, request):
        device_id = _device_id(request)
        if not device_id:
            raise CodedError("NOT_A_DEVICE", "Only the app sends a push token.", 400)
        token = request.data.get("token") if isinstance(request.data, dict) else None
        if not isinstance(token, str) or not 0 < len(token) <= 4096:
            raise CodedError("INVALID_TOKEN", "Send the phone's push token.", 400)
        Device.objects.filter(push_token=token).exclude(pk=device_id).update(push_token="")
        Device.objects.filter(pk=device_id, user=request.user).update(push_token=token)
        return Response(status=204)


def _row(n: Notification) -> dict:
    return {"id": n.id, "kind": n.kind, "title": n.title, "body": n.body,
            "booking": str(n.booking_id) if n.booking_id else None,
            "created_at": n.created_at, "read": n.read_at is not None}


class NotificationsView(APIView):
    """The bell: the person's latest notifications, newest first, and how many are unread."""

    def get(self, request):
        mine = Notification.objects.filter(user=request.user)
        return Response({"unread": mine.filter(read_at__isnull=True).count(),
                         "results": [_row(n) for n in mine.order_by("-created_at")[:LIMIT]]})


class ReadView(APIView):
    """Mark some ({"ids": [...]}) or all ({"all": true}) of your notifications read."""

    def post(self, request):
        body = request.data if isinstance(request.data, dict) else {}
        mine = Notification.objects.filter(user=request.user, read_at__isnull=True)
        ids = body.get("ids")
        if body.get("all") is not True:
            if not isinstance(ids, list) or not all(type(i) is int for i in ids):
                raise CodedError("INVALID_IDS", "Send the ids to mark read, or all: true.", 400)
            mine = mine.filter(pk__in=ids)
        mine.update(read_at=timezone.now())
        return Response({"unread": Notification.objects.filter(
            user=request.user, read_at__isnull=True).count()})


def _latest():
    from .models import AppRelease

    return AppRelease.objects.order_by("-version_code").first()


class AppLatestView(APIView):
    """What the phone needs to offer an update: the newest build, its checksum, and the oldest
    version still allowed to start jobs."""

    allow_password_change_pending = True

    def get(self, request):
        from django.conf import settings

        from apps.media import storage

        r = _latest()
        if r is None:
            return Response({"version_code": None, "min_version": settings.MIN_APP_VERSION})
        return Response({"version_code": r.version_code, "version_name": r.version_name,
                         "size": r.size, "sha256": r.sha256,
                         "notes": [x for x in r.notes.splitlines() if x.strip()],
                         "url": storage.presign_get(r.file_key, f"vayu-{r.version_name}.apk"),
                         "min_version": settings.MIN_APP_VERSION})


class AppDownloadView(APIView):
    """The web download link: sends the browser to the newest APK."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, request):
        from django.http import HttpResponseRedirect

        from apps.media import storage

        r = _latest()
        if r is None:
            raise CodedError("NO_APP", "No app build has been published yet.", 404)
        return HttpResponseRedirect(storage.presign_get(r.file_key, f"vayu-{r.version_name}.apk"))
