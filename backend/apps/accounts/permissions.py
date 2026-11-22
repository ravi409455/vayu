from rest_framework.permissions import BasePermission

from apps.core.errors import CodedError

from .models import Role


def enforce_password_change(request, view) -> None:
    """A user who must change their password can only reach views that opt in with
    `allow_password_change_pending = True`."""
    user = request.user
    if (user.is_authenticated and user.must_change_password
            and not getattr(view, "allow_password_change_pending", False)):
        raise CodedError("PASSWORD_CHANGE_REQUIRED", "You must change your password first.", 403)


class PasswordChangeNotRequired(BasePermission):
    """Global default. Views that set their own permission_classes (or get_permissions) must
    use the role classes below, which apply the same rule."""

    def has_permission(self, request, view):
        enforce_password_change(request, view)
        return True


class RolePermission(BasePermission):
    roles: tuple[str, ...] = ()

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        enforce_password_change(request, view)
        return request.user.role in self.roles


class IsAdmin(RolePermission):
    roles = (Role.ADMIN,)


class IsOpsOrAdmin(RolePermission):
    roles = (Role.OPS, Role.ADMIN)


class OpsReadAdminWrite(RolePermission):
    def has_permission(self, request, view):
        self.roles = ((Role.OPS, Role.ADMIN) if request.method in ("GET", "HEAD", "OPTIONS")
                      else (Role.ADMIN,))
        return super().has_permission(request, view)


class AnyReadAdminWrite(RolePermission):
    def has_permission(self, request, view):
        self.roles = (tuple(Role) if request.method in ("GET", "HEAD", "OPTIONS")
                      else (Role.ADMIN,))
        return super().has_permission(request, view)
