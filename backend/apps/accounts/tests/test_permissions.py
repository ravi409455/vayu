"""Configurable per-role permissions: catalog, grants, enforcement, roles API."""
import pytest
from rest_framework.test import APIClient

from apps.accounts.catalog import CATALOG, DEFAULTS, KEYS
from apps.accounts.models import AuditLog, Role, RolePermission
from apps.accounts.permissions import scope_for

pytestmark = pytest.mark.django_db

OPS_ALLOWED = {
    "bookings.view": "all", "bookings.create": "all", "bookings.edit": "all",
    "bookings.assign": "all", "bookings.reschedule": "all", "bookings.cancel": "all",
    "bookings.force_release": "all", "submissions.view": "all", "submissions.edit": "all",
    "media.manage": "all", "media.download": "all", "payments.verify": "all",
    "ratings.override": "all", "reports.view": "all", "reports.regenerate": "all",
    "dashboards.view": "all", "dashboards.export": "all", "users.view": "all",
    "users.sign_out_devices": "all", "forms.view": "all", "library.view": "all",
}
OPS_DENIED = [
    "forms.edit", "forms.publish", "forms.promote", "library.edit", "pdf_templates.view",
    "pdf_templates.edit", "master_lists.manage", "bookings.delete", "submissions.delete",
    "submissions.fill", "users.manage", "roles.manage", "audit.view", "integrations.manage",
    "api_keys.manage", "payments.record",
]
EXPERT_ALLOWED = {"bookings.view": "own", "submissions.view": "own", "submissions.fill": "own",
                  "payments.record": "own"}


def put_perms(client, role, permissions):
    return client.put(f"/api/v1/roles/{role}/permissions", {"permissions": permissions},
                      format="json")


# ---------------------------------------------------------------- catalog and defaults

def test_catalog_is_consistent():
    assert len(CATALOG) >= 30 and len(KEYS) == len(CATALOG)  # keys are unique
    for role, grants in DEFAULTS.items():
        assert role in (Role.OPS, Role.EXPERT)
        for key, scope in grants.items():
            assert key in KEYS and KEYS[key].grantable
            assert scope == "all" or (scope == "own" and KEYS[key].scoped)


def test_migration_seeded_exactly_the_defaults():
    seeded: dict = {}
    for row in RolePermission.objects.all():
        seeded.setdefault(row.role, {})[row.permission] = row.scope
    assert seeded == {r: dict(g) for r, g in DEFAULTS.items()}


def test_ops_defaults_are_daily_operations_only(make_user):
    ops = make_user(Role.OPS)
    for key, scope in OPS_ALLOWED.items():
        assert scope_for(ops, key) == scope, key
    for key in OPS_DENIED:
        assert scope_for(ops, key) is None, key


def test_ops_cannot_change_templates_or_delete_submissions_by_default(make_user):
    ops = make_user(Role.OPS)
    for key in ("forms.edit", "forms.publish", "library.edit", "pdf_templates.edit",
                "master_lists.manage", "submissions.delete", "bookings.delete"):
        assert scope_for(ops, key) is None


def test_expert_defaults(make_user):
    expert = make_user(Role.EXPERT)
    for key in KEYS:
        assert scope_for(expert, key) == EXPERT_ALLOWED.get(key), key


def test_admin_has_every_permission_even_with_no_rows(make_user):
    RolePermission.objects.all().delete()
    admin = make_user(Role.ADMIN)
    assert all(scope_for(admin, key) == "all" for key in KEYS)


def test_unknown_permission_key_is_a_programming_error(make_user):
    with pytest.raises(KeyError):
        scope_for(make_user(Role.OPS), "bookings.teleport")


def test_ungrantable_permissions_never_apply_to_non_admins_even_if_stored(make_user):
    RolePermission.objects.create(role=Role.OPS, permission="roles.manage", scope="all")
    assert scope_for(make_user(Role.OPS), "roles.manage") is None


# ---------------------------------------------------------------- roles API

def test_catalog_endpoint(api_as):
    admin, _ = api_as(Role.ADMIN)
    body = admin.get("/api/v1/permissions").json()
    by_key = {p["key"]: p for p in body}
    assert set(by_key) == set(KEYS)
    assert by_key["bookings.view"]["scoped"] is True and by_key["forms.edit"]["scoped"] is False
    assert by_key["roles.manage"]["grantable"] is False
    assert {"group", "label"} <= set(by_key["forms.edit"])


def test_roles_endpoint_lists_all_three_roles(api_as):
    admin, _ = api_as(Role.ADMIN)
    roles = {r["role"]: r for r in admin.get("/api/v1/roles").json()}
    assert set(roles) == {"admin", "ops", "expert"}
    assert roles["admin"]["locked"] is True and roles["ops"]["locked"] is False
    assert set(roles["admin"]["permissions"]) == set(KEYS)
    assert roles["ops"]["permissions"] == {k: v for k, v in DEFAULTS["ops"].items()}


@pytest.mark.parametrize("role", [Role.OPS, Role.EXPERT])
def test_only_roles_managers_can_read_or_edit_roles(api_as, role):
    client, _ = api_as(role)
    assert client.get("/api/v1/roles").status_code == 403
    assert client.get("/api/v1/permissions").status_code == 403
    assert put_perms(client, "ops", {}).status_code == 403


def test_granting_and_revoking_takes_effect_on_the_next_request(api_as):
    admin, _ = api_as(Role.ADMIN)
    ops, _ = api_as(Role.OPS)
    new_form = {"key": "ppi", "kind": "inspection", "name": "PPI"}
    assert ops.post("/api/v1/forms", new_form, format="json").status_code == 403
    perms = dict(DEFAULTS["ops"], **{"forms.edit": "all"})
    assert put_perms(admin, "ops", perms).status_code == 200
    assert ops.post("/api/v1/forms", new_form, format="json").status_code == 201
    assert put_perms(admin, "ops", dict(DEFAULTS["ops"])).status_code == 200
    assert ops.post("/api/v1/forms", {**new_form, "key": "ppi2"}, format="json").status_code == 403


def test_put_replaces_the_whole_set(api_as):
    admin, _ = api_as(Role.ADMIN)
    ops, _ = api_as(Role.OPS)
    assert ops.get("/api/v1/forms").status_code == 200
    put_perms(admin, "ops", {"library.view": "all"})
    assert ops.get("/api/v1/forms").status_code == 403  # forms.view was dropped
    assert ops.get("/api/v1/library").status_code == 200
    roles = {r["role"]: r for r in admin.get("/api/v1/roles").json()}
    assert roles["ops"]["permissions"] == {"library.view": "all"}


def test_scope_can_be_narrowed_to_own(api_as, make_user):
    admin, _ = api_as(Role.ADMIN)
    put_perms(admin, "ops", {"bookings.view": "own"})
    assert scope_for(make_user(Role.OPS), "bookings.view") == "own"


@pytest.mark.parametrize("payload,code", [
    ({"bookings.teleport": "all"}, "INVALID_PERMISSION"),
    ({"forms.edit": "own"}, "INVALID_SCOPE"),          # not a scoped permission
    ({"bookings.view": "everyone"}, "INVALID_SCOPE"),
    ({"bookings.view": True}, "INVALID_SCOPE"),
    ({"roles.manage": "all"}, "NOT_GRANTABLE"),
])
def test_invalid_grants_are_rejected_and_change_nothing(api_as, payload, code):
    admin, _ = api_as(Role.ADMIN)
    r = put_perms(admin, "ops", payload)
    assert r.status_code == 400 and r.json()["code"] == code
    roles = {x["role"]: x for x in admin.get("/api/v1/roles").json()}
    assert roles["ops"]["permissions"] == dict(DEFAULTS["ops"])


def test_body_must_hold_a_permissions_object(api_as):
    admin, _ = api_as(Role.ADMIN)
    assert admin.put("/api/v1/roles/ops/permissions", {"permissions": ["x"]},
                     format="json").status_code == 400
    assert admin.put("/api/v1/roles/ops/permissions", {}, format="json").status_code == 400


def test_admin_role_is_locked_and_unknown_roles_404(api_as):
    admin, _ = api_as(Role.ADMIN)
    r = put_perms(admin, "admin", {"forms.view": "all"})
    assert r.status_code == 400 and r.json()["code"] == "ADMIN_ROLE_LOCKED"
    assert put_perms(admin, "superhero", {}).status_code == 404


def test_changes_are_audited_with_a_diff(api_as):
    admin, me = api_as(Role.ADMIN)
    perms = dict(DEFAULTS["ops"], **{"forms.edit": "all"})
    perms.pop("dashboards.export")
    put_perms(admin, "ops", perms)
    row = AuditLog.objects.get(action="role.permissions_update")
    assert row.actor == me and row.target_id == "ops"
    assert "+forms.edit" in row.summary and "-dashboards.export" in row.summary


def test_me_returns_the_effective_permissions(api_as, make_user, login):
    ops = make_user(Role.OPS, username="opsy")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login(client, 'opsy').json()['access']}")
    perms = client.get("/api/v1/auth/me").json()["permissions"]
    assert perms == dict(DEFAULTS["ops"]) and ops.role == "ops"
    admin_client, _ = api_as(Role.ADMIN)
    assert set(admin_client.get("/api/v1/auth/me").json()["permissions"]) == set(KEYS)


# ---------------------------------------------------------------- enforcement on endpoints

def test_forms_are_readable_by_ops_never_by_experts_and_editable_only_when_granted(api_as):
    admin, _ = api_as(Role.ADMIN)
    ops, _ = api_as(Role.OPS)
    expert, _ = api_as(Role.EXPERT)
    form = admin.post("/api/v1/forms", {"key": "pdi", "kind": "inspection", "name": "PDI"},
                      format="json").json()
    v = form["draft_version"]["id"]
    assert ops.get(f"/api/v1/form-versions/{v}").status_code == 200
    assert expert.get(f"/api/v1/form-versions/{v}").status_code == 403
    assert ops.post(f"/api/v1/form-versions/{v}/pages", {"title": "x"},
                    format="json").status_code == 403
    assert ops.post(f"/api/v1/form-versions/{v}/publish", {"row_version": 0},
                    format="json").status_code == 403
    put_perms(admin, "ops", dict(DEFAULTS["ops"], **{"forms.publish": "all"}))
    assert ops.post(f"/api/v1/form-versions/{v}/publish", {"row_version": 0},
                    format="json").status_code != 403  # allowed through (stale draft -> 409)


def test_saving_to_the_library_needs_both_forms_edit_and_library_edit(api_as):
    admin, _ = api_as(Role.ADMIN)
    ops, _ = api_as(Role.OPS)
    form = admin.post("/api/v1/forms", {"key": "pdi", "kind": "inspection", "name": "PDI"},
                      format="json").json()
    t = admin.get(f"/api/v1/form-versions/{form['draft_version']['id']}").json()
    sid = t["pages"][0]["sections"][0]["id"]
    f = admin.post(f"/api/v1/sections/{sid}/fields",
                   {"key": "paint", "label": "Paint", "type": "short_text"}, format="json").json()
    url = f"/api/v1/fields/{f['id']}/save-to-library"
    put_perms(admin, "ops", dict(DEFAULTS["ops"], **{"forms.edit": "all"}))
    assert ops.post(url, {}, format="json").status_code == 403  # library.edit missing
    put_perms(admin, "ops", dict(DEFAULTS["ops"], **{"forms.edit": "all", "library.edit": "all"}))
    assert ops.post(url, {}, format="json").status_code == 201


def test_master_lists_readable_by_everyone_writable_only_when_granted(api_as):
    admin, _ = api_as(Role.ADMIN)
    ops, _ = api_as(Role.OPS)
    expert, _ = api_as(Role.EXPERT)
    admin.post("/api/v1/master-lists", {"key": "city", "name": "City"}, format="json")
    assert expert.get("/api/v1/master-lists/city/items").status_code == 200
    body = {"key": "reason", "name": "Reason"}
    assert ops.post("/api/v1/master-lists", body, format="json").status_code == 403
    put_perms(admin, "ops", dict(DEFAULTS["ops"], **{"master_lists.manage": "all"}))
    assert ops.post("/api/v1/master-lists", body, format="json").status_code == 201


def test_library_visibility_follows_library_view(api_as):
    ops, _ = api_as(Role.OPS)
    expert, _ = api_as(Role.EXPERT)
    assert ops.get("/api/v1/library").status_code == 200
    assert expert.get("/api/v1/library").status_code == 403


def test_audit_log_needs_audit_view(api_as):
    admin, _ = api_as(Role.ADMIN)
    ops, _ = api_as(Role.OPS)
    assert ops.get("/api/v1/audit-logs").status_code == 403
    put_perms(admin, "ops", dict(DEFAULTS["ops"], **{"audit.view": "all"}))
    assert ops.get("/api/v1/audit-logs").status_code == 200


def test_a_forced_password_change_blocks_even_permitted_users(make_user, login):
    make_user(Role.OPS, username="opsy", must_change_password=True)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login(client, 'opsy').json()['access']}")
    r = client.get("/api/v1/forms")
    assert r.status_code == 403 and r.json()["code"] == "PASSWORD_CHANGE_REQUIRED"


# ---------------------------------------------------------------- no privilege escalation

@pytest.fixture
def ops_user_manager(api_as, make_user):
    """An Ops user who has been granted users.manage."""
    admin, _ = api_as(Role.ADMIN)
    put_perms(admin, "ops", dict(DEFAULTS["ops"], **{"users.manage": "all"}))
    ops, ops_user = api_as(Role.OPS)
    return ops, ops_user, make_user(Role.ADMIN, username="theboss")


NEW = {"username": "newbie", "name": "N", "role": "expert", "password": "Temp-pass-123"}


def test_users_manage_holder_can_manage_non_admin_users(ops_user_manager, make_user):
    ops, _, _ = ops_user_manager
    assert ops.post("/api/v1/users", NEW, format="json").status_code == 201
    target = make_user(Role.EXPERT)
    assert ops.patch(f"/api/v1/users/{target.id}", {"name": "X"}, format="json").status_code == 200


def test_only_an_admin_can_create_or_touch_admin_users(ops_user_manager, make_user):
    ops, _, boss = ops_user_manager
    expert = make_user(Role.EXPERT)
    attempts = [
        ops.post("/api/v1/users", {**NEW, "role": "admin"}, format="json"),
        ops.patch(f"/api/v1/users/{boss.id}", {"name": "pwned"}, format="json"),
        ops.patch(f"/api/v1/users/{expert.id}", {"role": "admin"}, format="json"),
        ops.post(f"/api/v1/users/{boss.id}/reset-password", {"password": "Temp-pass-123"},
                 format="json"),
        ops.post(f"/api/v1/users/{boss.id}/sign-out-devices"),
    ]
    for r in attempts:
        assert r.status_code == 403 and r.json()["code"] == "ADMIN_ONLY"
    boss.refresh_from_db()
    assert boss.name != "pwned"


def test_ops_without_users_manage_cannot_manage_users(api_as, make_user):
    ops, _ = api_as(Role.OPS)
    target = make_user(Role.EXPERT)
    assert ops.post("/api/v1/users", NEW, format="json").status_code == 403
    r = ops.patch(f"/api/v1/users/{target.id}", {"name": "X"}, format="json")
    assert r.status_code == 403
    assert ops.get("/api/v1/users").status_code == 200  # users.view
    assert ops.post(f"/api/v1/users/{target.id}/sign-out-devices").status_code == 200


# ------------------------------------------------------ every endpoint declares its permission

PUBLIC_OR_AUTHENTICATED_ONLY = {"HealthView", "LoginView", "DeviceCheckedRefreshView", "MeView",
                                "LogoutView", "ChangePasswordView", "ZipDownload", "Verify"}


def _all_views():
    from django.urls import URLPattern, URLResolver, get_resolver

    seen = {}

    def walk(patterns):
        for p in patterns:
            if isinstance(p, URLResolver):
                walk(p.url_patterns)
            elif isinstance(p, URLPattern):
                cls = getattr(p.callback, "cls", None) or getattr(p.callback, "view_class", None)
                if cls is not None:
                    seen[cls.__name__] = cls

    walk(get_resolver().url_patterns)
    return seen


def declared(view) -> set[str]:
    keys = set(getattr(view, "declared_permissions", ()))
    for cls in getattr(view, "permission_classes", []):
        for k in getattr(cls, "perm_keys", ()):
            keys.add(k)
    return keys


def test_every_view_declares_catalog_permissions_or_is_explicitly_exempt():
    views = _all_views()
    assert len(views) > 25
    for name, view in views.items():
        if name in PUBLIC_OR_AUTHENTICATED_ONLY:
            continue
        keys = declared(view)
        assert keys, f"{name} declares no permission"
        assert keys <= set(KEYS), f"{name} declares unknown permissions {keys - set(KEYS)}"


def test_the_exempt_list_is_current():
    assert PUBLIC_OR_AUTHENTICATED_ONLY <= set(_all_views())


def test_perm_needs_at_least_one_permission():
    from apps.accounts.permissions import perm

    with pytest.raises(ValueError):
        perm(None)


def test_anonymous_requests_are_rejected_before_any_permission_check():
    for path in ("/api/v1/forms", "/api/v1/roles", "/api/v1/users", "/api/v1/audit-logs"):
        assert APIClient().get(path).status_code == 401


def test_scope_is_loaded_once_per_request(make_user, django_assert_num_queries):
    from django.test import RequestFactory

    ops = make_user(Role.OPS)
    request = RequestFactory().get("/")
    with django_assert_num_queries(1):
        scope_for(ops, "forms.view", request)
        scope_for(ops, "bookings.view", request)
        scope_for(ops, "bookings.delete", request)


def test_perm_any_needs_one_of_the_permissions(api_as):
    from django.test import RequestFactory

    from apps.accounts.permissions import perm_any

    expert, user = api_as(Role.EXPERT)
    request = RequestFactory().get("/")
    request.user = user
    assert perm_any("bookings.delete", "submissions.fill")().has_permission(request, None)
    assert not perm_any("bookings.delete", "forms.edit")().has_permission(request, None)
    from django.contrib.auth.models import AnonymousUser

    request.user = AnonymousUser()
    assert not perm_any("submissions.fill")().has_permission(request, None)
