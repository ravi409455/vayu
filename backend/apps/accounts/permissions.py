"""Permission checks. Every API view declares the catalog permission(s) it needs with `perm()`;
a test scans the URL conf so a new endpoint cannot be forgotten."""
from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.core.errors import CodedError

from .catalog import KEYS
from .models import Role, RolePermission


def enforce_password_change(request, view) -> None:
    """A user who must change their password can only reach views that opt in with
    `allow_password_change_pending = True`."""
    user = request.user
    if (user.is_authenticated and user.must_change_password
            and not getattr(view, "allow_password_change_pending", False)):
        raise CodedError("PASSWORD_CHANGE_REQUIRED", "You must change your password first.", 403)


def grants_for(role: str) -> dict[str, str]:
    """{permission: "all"|"own"} for a role. Admin always has everything; ungrantable permissions
    are never honoured for anyone else, even if a row exists."""
    if role == Role.ADMIN:
        return {k: "all" for k in KEYS}
    rows = RolePermission.objects.filter(role=role).values_list("permission", "scope")
    return {k: s for k, s in rows if k in KEYS and KEYS[k].grantable}


def scope_for(user, key: str, request=None) -> str | None:
    """"all", "own" or None (not allowed). Unknown keys raise KeyError (a programming error).
    Pass the request to load a role's grants once per request."""
    KEYS[key]  # noqa: B018 - raises KeyError for unknown keys
    if user.role == Role.ADMIN:
        return "all"
    cache = getattr(request, "_vayu_grants", None) if request is not None else None
    if cache is None:
        cache = grants_for(user.role)
        if request is not None:
            request._vayu_grants = cache
    return cache.get(key)


class PasswordChangeNotRequired(BasePermission):
    """Global default. Views that set their own permission_classes must use perm(), which
    applies the same rule."""

    def has_permission(self, request, view):
        enforce_password_change(request, view)
        return True


def perm(read: str | None, write: str | tuple[str, ...] | None = None):
    """Permission class: safe methods need `read` (None = any signed-in user); other methods need
    `write` (all of them if several), or `read` when write is not given."""
    write_keys: tuple[str, ...] = (write,) if isinstance(write, str) else tuple(write or ())
    if read is None and not write_keys:
        raise ValueError("perm() needs at least one permission")

    class _Perm(BasePermission):
        perm_keys = tuple(k for k in (read, *write_keys) if k)

        def has_permission(self, request, view):
            if not request.user.is_authenticated:
                return False
            enforce_password_change(request, view)
            required: tuple[str, ...]
            if request.method in SAFE_METHODS:
                required = (read,) if read else ()
            else:
                required = write_keys or ((read,) if read else ())
            return all(scope_for(request.user, k, request) for k in required)

    return _Perm
