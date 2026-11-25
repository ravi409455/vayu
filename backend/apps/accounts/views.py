from django.conf import settings
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.contrib.auth import update_session_auth_hash
from django.db import transaction
from django.http import HttpResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework import serializers as s_
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenRefreshView

from apps.core import log
from apps.core.errors import CodedError
from apps.platform.schema import obj

from . import audit, avatars, roles, services
from .authentication import DeviceCheckedRefreshSerializer
from .catalog import CATALOG
from .models import AuditLog, Device, Role, Theme, User
from .permissions import PasswordChangeNotRequired, grants_for, perm, perm_any, scope_for
from .serializers import (
    AuditLogSerializer,
    ChangePasswordSerializer,
    LoginSerializer,
    MeSerializer,
    PasswordSerializer,
    UserSerializer,
)


def _same_origin(request) -> None:
    """Login CSRF (F-058): a browser posting from another site may not sign it in. Browsers send
    Origin on every cross-site POST; an app or a script sends none."""
    from urllib.parse import urlparse

    from django.conf import settings

    origin = request.headers.get("Origin")
    if origin and urlparse(origin).netloc != request.get_host() and origin not in getattr(
            settings, "CSRF_TRUSTED_ORIGINS", []):
        raise CodedError("BAD_ORIGIN", "Sign in from the Vayu page itself.", 403)


@extend_schema(responses=obj(
    "Login", user=s_.DictField(), must_change_password=s_.BooleanField(),
    access=s_.CharField(required=False), refresh=s_.CharField(required=False)))
class LoginView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        s = LoginSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        if s.validated_data["client"] == "web":
            _same_origin(request)
        user = services.authenticate(s.validated_data["username"], s.validated_data["password"],
                                     self.get_throttles()[0].get_ident(request))
        data = {"user": UserSerializer(user).data,
                "must_change_password": user.must_change_password}
        if s.validated_data["client"] == "web":
            django_login(request._request, user,
                         backend="django.contrib.auth.backends.ModelBackend")
            get_token(request._request)  # make sure the CSRF cookie is set
        elif user.role == Role.ADMIN:
            # the app is for Ops and experts; Admin tools are web-only
            raise CodedError("ADMIN_USE_WEB", "The app is for Ops and experts. Admins use the web.",
                             403)
        else:
            data.update(services.register_device_and_tokens(user, s.validated_data["device_name"]))
        return Response(data)


class DeviceCheckedRefreshView(TokenRefreshView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"
    serializer_class = DeviceCheckedRefreshSerializer


@extend_schema(responses=obj("Me", id=s_.IntegerField(), username=s_.CharField(),
                             role=s_.CharField(), permissions=s_.DictField(child=s_.CharField())))
class MeView(APIView):
    allow_password_change_pending = True

    def get(self, request):
        return Response({**MeSerializer(request.user).data,
                         "permissions": grants_for(request.user.role)})


class ProfileView(APIView):
    """What a person may change about themselves: their theme, and (Ops) which notifications they
    get. Name, email, role and phone are the Admin's to change."""

    def patch(self, request):
        from apps.notify.handlers import PREFS

        body = request.data if isinstance(request.data, dict) else {}
        extra = sorted(set(body) - {"theme", "notify_prefs"})
        if extra:
            raise CodedError("FIELD_NOT_EDITABLE", "Only an Admin can change that. You can change "
                             "your theme here.", 400, keys=extra)
        user = request.user
        if "notify_prefs" not in body and "theme" not in body:
            raise ValidationError({"theme": f"Choose one of: {', '.join(Theme.values)}."})
        if "theme" in body:
            theme = body["theme"]
            if theme not in Theme.values:
                raise ValidationError({"theme": f"Choose one of: {', '.join(Theme.values)}."})
            if user.theme != theme:
                user.theme = theme
                user.save(update_fields=["theme"])
                audit.record(user, "user.theme_change", "user", user.id, f"Theme set to {theme}")
        if "notify_prefs" in body:
            prefs = body["notify_prefs"]
            if user.role != Role.OPS:
                raise CodedError("FIELD_NOT_EDITABLE", "Only Ops choose their notifications.", 400,
                                 keys=["notify_prefs"])
            if not isinstance(prefs, dict) or any(k not in PREFS or type(v) is not bool
                                                  for k, v in prefs.items()):
                raise ValidationError({"notify_prefs": "Switch these on or off: "
                                       f"{', '.join(PREFS)}. Problems are always on."})
            user.notify_prefs = {**user.notify_prefs, **prefs}
            user.save(update_fields=["notify_prefs"])
        return Response(MeSerializer(user).data)


class MyPictureView(APIView):
    """Your own picture: upload a file (it is cropped square and shrunk) or remove it."""

    parser_classes = [MultiPartParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "avatar"

    def put(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            raise CodedError("INVALID_IMAGE", "Choose a picture to upload.", 400)
        if upload.size > avatars.MAX_BYTES:
            raise CodedError("IMAGE_TOO_LARGE", "The picture must be 5 MB or smaller.", 413)
        user = request.user
        user.avatar = avatars.process(upload.read())
        user.has_avatar, user.avatar_version = True, user.avatar_version + 1
        user.save(update_fields=["avatar", "has_avatar", "avatar_version"])
        audit.record(user, "user.picture_set", "user", user.id, "Set their profile picture")
        return Response(MeSerializer(user).data)

    def delete(self, request):
        user = request.user
        if user.has_avatar:
            user.avatar, user.has_avatar, user.avatar_version = None, False, user.avatar_version + 1
            user.save(update_fields=["avatar", "has_avatar", "avatar_version"])
            audit.record(user, "user.picture_removed", "user", user.id,
                         "Removed their profile picture")
        return Response(MeSerializer(user).data)


class LogoutView(APIView):
    allow_password_change_pending = True

    def post(self, request):
        token = request.auth
        device_id = token.get("device_id") if hasattr(token, "get") else None
        if device_id:
            if Device.objects.filter(pk=device_id, revoked_at__isnull=True).update(
                    revoked_at=timezone.now(), push_token=""):
                log.event("auth.device_revoked", user=request.user, count=1)
        else:
            django_logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class HeartbeatView(APIView):
    """A phone says what it still holds (unsent drafts and files). Used to stop a second phone
    from signing in while this one could lose work, and to show the person's phone status."""

    allow_password_change_pending = True

    def post(self, request):
        token = request.auth
        device_id = token.get("device_id") if hasattr(token, "get") else None
        if not device_id:
            raise CodedError("NOT_A_DEVICE", "Only the app sends a heartbeat.", 400)
        body = request.data if isinstance(request.data, dict) else {}
        counts = {k: body.get(k) for k in ("drafts", "files")}
        if any(type(v) is not int or v < 0 for v in counts.values()):
            raise CodedError("INVALID_COUNTS", "drafts and files must be whole numbers, 0 or more.",
                             400)
        seen: dict = {"unsynced": counts, "last_seen_at": timezone.now()}
        version = body.get("app_version")
        if isinstance(version, str) and version.strip():      # optional; kept for metrics (F-247)
            seen["app_version"] = version.strip()[:32]
        Device.objects.filter(pk=device_id).update(**seen)
        return Response({"server_time": timezone.now(),
                         "min_app_version": settings.MIN_APP_VERSION})


class ChangePasswordView(APIView):
    allow_password_change_pending = True

    def post(self, request):
        s = ChangePasswordSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(s.validated_data["old_password"]):
            raise ValidationError({"old_password": "Incorrect password."})
        services.validate_new_password(s.validated_data["new_password"], user.username)
        user.set_password(s.validated_data["new_password"])
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password"])
        audit.record(user, "user.change_password", "user", user.id, "Changed their password")
        log.event("auth.password_changed", user=user, changed_by=user.pk)
        # a changed password signs out every other phone (this one keeps working)
        others = Device.objects.filter(user=user, revoked_at__isnull=True)
        if hasattr(request.auth, "get") and request.auth.get("device_id"):
            others = others.exclude(pk=request.auth.get("device_id"))
        others.update(revoked_at=timezone.now(), push_token="")
        if request._request.user.is_authenticated:  # keep the web session alive
            update_session_auth_hash(request._request, user)
        return Response({"detail": "Password changed."})


def _admin_only(request, *roles) -> None:
    """Only an Admin may create, change, reset or sign out an Admin user (no escalation)."""
    if request.user.role != Role.ADMIN and Role.ADMIN in roles:
        raise CodedError("ADMIN_ONLY", "Only an Admin can manage Admin users.", 403)


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    # users are never deleted (destroy answers 405); DELETE exists only for a user's picture
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    declared_permissions = ("users.view", "users.manage", "users.sign_out_devices")

    def get_queryset(self):
        qs = User.objects.order_by("username")
        role = self.request.query_params.get("role")
        return qs.filter(role=role) if role else qs

    def destroy(self, request, *args, **kwargs):
        raise MethodNotAllowed("DELETE")

    def get_permissions(self):
        if self.action == "picture" and self.request.method == "GET":
            return [IsAuthenticated(), PasswordChangeNotRequired()]   # the handler decides who
        if self.action in ("list", "retrieve"):
            return [perm("users.view")()]
        if self.action == "sign_out_devices":
            return [perm("users.sign_out_devices")()]
        if self.action == "phone":                     # read before deactivating or signing out
            return [perm_any("users.manage", "users.sign_out_devices")()]
        return [perm("users.manage")()]

    def perform_create(self, serializer):
        _admin_only(self.request, serializer.validated_data["role"])
        user = serializer.save()
        audit.record(self.request.user, "user.create", "user", user.id,
                     f"Created user {user.username} ({user.role})")

    @transaction.atomic
    def perform_update(self, serializer):
        user = serializer.instance
        was_active = user.is_active
        new_active = serializer.validated_data.get("is_active", was_active)
        new_role = serializer.validated_data.get("role", user.role)
        _admin_only(self.request, user.role, new_role)
        if user.pk == self.request.user.pk and not new_active:
            raise ValidationError({"is_active": "You cannot deactivate yourself."})
        if user.role == Role.ADMIN and was_active and (new_role != Role.ADMIN or not new_active):
            admins = list(User.objects.select_for_update().filter(role=Role.ADMIN, is_active=True))
            if not [a for a in admins if a.pk != user.pk]:
                raise CodedError("LAST_ADMIN", "There must always be one active admin.", 400)
        was_role = user.role
        user = serializer.save()
        if user.role != was_role:            # the app's tokens carry the old role (F-056)
            services.revoke_devices(user)
        if was_active and not user.is_active:
            services.revoke_devices(user)
            audit.record(self.request.user, "user.deactivate", "user", user.id,
                         f"Deactivated {user.username}")
        elif not was_active and user.is_active:
            audit.record(self.request.user, "user.activate", "user", user.id,
                         f"Reactivated {user.username}")
        else:
            audit.record(self.request.user, "user.update", "user", user.id,
                         f"Updated {user.username}")

    @action(detail=True, methods=["get", "delete"], url_path="picture")
    def picture(self, request, pk=None):
        """GET: the picture, for the person and for anyone who may see the user list (Ops, Admin);
        everyone else is told there is none. DELETE: an Admin removes someone's picture."""
        user = self.get_object()
        if request.method == "DELETE":
            if user.has_avatar:
                User.objects.filter(pk=user.pk).update(
                    avatar=None, has_avatar=False, avatar_version=user.avatar_version + 1)
                audit.record(request.user, "user.picture_removed_by_admin", "user", user.id,
                             f"Removed the profile picture of {user.username}")
            return Response(status=status.HTTP_204_NO_CONTENT)
        if request.user.pk != user.pk and not scope_for(request.user, "users.view", request):
            raise CodedError("NOT_FOUND", "No picture.", 404)
        row = User.objects.defer(None).filter(pk=user.pk).values("avatar", "avatar_version").first()
        assert row is not None  # noqa: S101 - invariant, narrows the type
        if not row["avatar"]:
            raise CodedError("NOT_FOUND", "No picture.", 404)
        etag = f'W/"{user.pk}-{row["avatar_version"]}"'
        headers = {"ETag": etag, "Cache-Control": "private, max-age=86400"}
        if request.headers.get("If-None-Match") == etag:
            return HttpResponse(status=304, headers=headers)
        return HttpResponse(bytes(row["avatar"]), content_type="image/jpeg", headers=headers)

    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        user = self.get_object()
        _admin_only(request, user.role)
        s = PasswordSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.validate_new_password(s.validated_data["password"], user.username)
        user.set_password(s.validated_data["password"])
        user.must_change_password = True
        user.failed_attempts = 0
        user.locked_until = None
        user.save()
        services.revoke_devices(user)
        log.event("auth.password_changed", user=user, changed_by=request.user.pk)
        audit.record(request.user, "user.reset_password", "user", user.id,
                     f"Reset password for {user.username}")
        return Response(UserSerializer(user).data)

    @action(detail=True, methods=["post"], url_path="sign-out-devices")
    def sign_out_devices(self, request, pk=None):
        user = self.get_object()
        _admin_only(request, user.role)
        count = services.revoke_devices(user)
        audit.record(request.user, "user.sign_out_devices", "user", user.id,
                     f"Signed out {count} device(s) of {user.username}")
        return Response({"revoked": count,
                         "warning": "Any unsynced data on those devices may be lost."})


    @extend_schema(responses=inline_serializer("PhoneState", {
        "devices": serializers.IntegerField(), "drafts": serializers.IntegerField(),
        "files": serializers.IntegerField(), "unknown": serializers.BooleanField(),
        "last_seen_at": serializers.DateTimeField(allow_null=True)}))
    @action(detail=True, methods=["get"])
    def phone(self, request, pk=None):
        """What the person's signed-in phones last said they still hold (F-243), so the deactivate
        and sign-out warnings say what would be lost. unknown: a phone never reported."""
        user = self.get_object()
        devices = list(Device.objects.filter(user=user, revoked_at__isnull=True))
        reported = [d.unsynced for d in devices if d.unsynced is not None]
        seen = [d.last_seen_at for d in devices if d.last_seen_at]
        return Response({"devices": len(devices),
                         "drafts": sum(int(u.get("drafts", 0) or 0) for u in reported),
                         "files": sum(int(u.get("files", 0) or 0) for u in reported),
                         "unknown": len(reported) < len(devices),
                         "last_seen_at": max(seen) if seen else None})


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditLogSerializer
    permission_classes = [perm("audit.view")]

    def get_queryset(self):
        p = self.request.query_params
        qs = AuditLog.objects.select_related("actor").order_by("-created_at", "-id")
        if p.get("actor"):
            if not p["actor"].isdigit():
                raise ValidationError({"actor": "Use a user id."})
            qs = qs.filter(actor_id=p["actor"])
        if p.get("action"):
            qs = qs.filter(action__startswith=p["action"])     # "api_key" finds api_key.create too
        if p.get("from"):
            qs = qs.filter(created_at__date__gte=p["from"])
        if p.get("to"):
            qs = qs.filter(created_at__date__lte=p["to"])
        return qs


class PermissionCatalogView(APIView):
    permission_classes = [perm("roles.manage")]

    def get(self, request):
        return Response([{"key": p.key, "group": p.group, "label": p.label, "scoped": p.scoped,
                          "grantable": p.grantable} for p in CATALOG])


class RolesView(APIView):
    permission_classes = [perm("roles.manage")]

    def get(self, request):
        return Response(roles.list_roles())


class RolePermissionsView(APIView):
    permission_classes = [perm("roles.manage")]

    def put(self, request, role):
        if "permissions" not in request.data:
            raise ValidationError({"permissions": "This field is required."})
        return Response(roles.set_role_permissions(request.user, role,
                                                   request.data["permissions"]))
