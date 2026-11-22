"""Editing what a role may do (Admin only, audited)."""
from django.db import transaction
from rest_framework.exceptions import NotFound

from apps.core.errors import CodedError

from . import audit
from .catalog import KEYS
from .models import Role, RolePermission
from .permissions import grants_for

EDITABLE = (Role.OPS, Role.EXPERT)


def list_roles() -> list[dict]:
    return [{"role": r, "locked": r == Role.ADMIN, "permissions": grants_for(r)}
            for r in (Role.ADMIN, Role.OPS, Role.EXPERT)]


def validate_grants(permissions) -> dict[str, str]:
    if not isinstance(permissions, dict):
        raise CodedError("INVALID_PERMISSIONS", "permissions must be an object.", 400)
    for key, scope in permissions.items():
        perm = KEYS.get(key)
        if perm is None:
            raise CodedError("INVALID_PERMISSION", f"Unknown permission '{key}'.", 400)
        if not perm.grantable:
            raise CodedError("NOT_GRANTABLE", f"'{key}' can only be held by Admin.", 400)
        allowed = ("own", "all") if perm.scoped else ("all",)
        if not isinstance(scope, str) or scope not in allowed:
            raise CodedError("INVALID_SCOPE", f"'{key}' must be one of: {', '.join(allowed)}.", 400)
    return permissions


@transaction.atomic
def set_role_permissions(actor, role: str, permissions) -> dict:
    if role not in Role.values:
        raise NotFound("Unknown role.")
    if role not in EDITABLE:
        raise CodedError("ADMIN_ROLE_LOCKED", "The Admin role always has full access.", 400)
    new = validate_grants(permissions)
    old = grants_for(role)
    RolePermission.objects.filter(role=role).delete()
    RolePermission.objects.bulk_create(
        [RolePermission(role=role, permission=k, scope=s) for k, s in new.items()])
    changes = ([f"+{k}({s})" for k, s in sorted(new.items()) if k not in old]
               + [f"-{k}" for k in sorted(old) if k not in new]
               + [f"~{k}({old[k]}->{s})" for k, s in sorted(new.items())
                  if k in old and old[k] != s])
    audit.record(actor, "role.permissions_update", "role", role,
                 f"{role}: {' '.join(changes) or 'no change'}")
    return {"role": role, "locked": False, "permissions": grants_for(role)}
