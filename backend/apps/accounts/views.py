from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.contrib.auth import update_session_auth_hash
from django.db import transaction
from django.middleware.csrf import get_token
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenRefreshView

from apps.core.errors import CodedError

from . import audit, roles, services
from .authentication import DeviceCheckedRefreshSerializer
from .catalog import CATALOG
from .models import AuditLog, Device, Role, User
from .permissions import grants_for, perm
from .serializers import (
    AuditLogSerializer,
    ChangePasswordSerializer,
    LoginSerializer,
    PasswordSerializer,
    UserSerializer,
)


class LoginView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def post(self, request):
        s = LoginSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = services.authenticate(s.validated_data["username"], s.validated_data["password"])
        data = {"user": UserSerializer(user).data,
                "must_change_password": user.must_change_password}
        if s.validated_data["client"] == "web":
            django_login(request._request, user,
                         backend="django.contrib.auth.backends.ModelBackend")
            get_token(request._request)  # make sure the CSRF cookie is set
        else:
            data.update(services.register_device_and_tokens(user, s.validated_data["device_name"]))
        return Response(data)


class DeviceCheckedRefreshView(TokenRefreshView):
    serializer_class = DeviceCheckedRefreshSerializer


class MeView(APIView):
    allow_password_change_pending = True

    def get(self, request):
        return Response({**UserSerializer(request.user).data,
                         "permissions": grants_for(request.user.role)})


class LogoutView(APIView):
    allow_password_change_pending = True

    def post(self, request):
        token = request.auth
        device_id = token.get("device_id") if hasattr(token, "get") else None
        if device_id:
            Device.objects.filter(pk=device_id, revoked_at__isnull=True).update(
                revoked_at=timezone.now())
        else:
            django_logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


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
        if request._request.user.is_authenticated:  # keep the web session alive
            update_session_auth_hash(request._request, user)
        return Response({"detail": "Password changed."})


def _admin_only(request, *roles) -> None:
    """Only an Admin may create, change, reset or sign out an Admin user (no escalation)."""
    if request.user.role != Role.ADMIN and Role.ADMIN in roles:
        raise CodedError("ADMIN_ONLY", "Only an Admin can manage Admin users.", 403)


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]  # users are never deleted
    declared_permissions = ("users.view", "users.manage", "users.sign_out_devices")

    def get_queryset(self):
        qs = User.objects.order_by("username")
        role = self.request.query_params.get("role")
        return qs.filter(role=role) if role else qs

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [perm("users.view")()]
        if self.action == "sign_out_devices":
            return [perm("users.sign_out_devices")()]
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
        user = serializer.save()
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


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditLogSerializer
    permission_classes = [perm("audit.view")]

    def get_queryset(self):
        p = self.request.query_params
        qs = AuditLog.objects.select_related("actor").order_by("-created_at", "-id")
        if p.get("actor"):
            qs = qs.filter(actor_id=p["actor"])
        if p.get("action"):
            qs = qs.filter(action=p["action"])
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
