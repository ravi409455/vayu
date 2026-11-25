"""Plan batch 5: Admin-only permissions and changed Ops defaults (F-054, R-34, R-23, F-223)."""
from importlib import import_module

import pytest
from django.apps import apps as django_apps

from apps.accounts.catalog import DEFAULTS, KEYS
from apps.accounts.models import RolePermission

pytestmark = pytest.mark.django_db
MIGRATION = "apps.accounts.migrations.0014_batch5_permissions"


@pytest.mark.parametrize("key", import_module(MIGRATION).ADMIN_ONLY)
def test_integrations_keys_forms_templates_and_lists_are_admin_only(key):
    assert KEYS[key].grantable is False


def test_ops_no_longer_sign_users_out_by_default_and_submissions_delete_is_gone():
    assert "users.sign_out_devices" not in DEFAULTS["ops"]
    assert "submissions.delete" not in KEYS


def test_the_roles_screen_refuses_to_grant_them(api_as):
    admin, _ = api_as("admin")
    r = admin.put("/api/v1/roles/ops/permissions", {"permissions": {
        "bookings.view": "all", "api_keys.manage": "all"}}, format="json")
    assert r.status_code == 400


def test_the_migration_removes_existing_grants_in_order_and_can_turn_sign_out_back_on():
    m = import_module(MIGRATION)
    for perm in ("api_keys.manage", "forms.edit", "users.sign_out_devices",
                 "submissions.delete", "bookings.view"):
        RolePermission.objects.get_or_create(role="ops", permission=perm,
                                             defaults={"scope": "all"})
    m.admin_only(django_apps, None)
    m.sign_out_off(django_apps, None)
    m.drop_submissions_delete(django_apps, None)
    left = set(RolePermission.objects.filter(role="ops").values_list("permission", flat=True))
    assert left & {"api_keys.manage", "forms.edit", "users.sign_out_devices",
                   "submissions.delete"} == set() and "bookings.view" in left
    from django.db import connection

    with connection.schema_editor() as editor:
        m.sign_out_on(django_apps, editor)
    assert RolePermission.objects.filter(role="ops", permission="users.sign_out_devices").exists()


# ---------------------------------------------------------------- sign-in and roles

def test_a_web_sign_in_posted_from_another_site_is_refused(make_user, login):
    """F-058 login CSRF."""
    from rest_framework.test import APIClient

    from apps.core.testing import PASSWORD

    make_user(username="asha")

    def web(client):
        return client.post("/api/v1/auth/login", {"username": "asha", "password": PASSWORD,
                                                  "client": "web"}, format="json")

    evil = APIClient(HTTP_ORIGIN="https://evil.example")
    r = web(evil)
    assert r.status_code == 403 and r.json()["code"] == "BAD_ORIGIN"
    assert login(evil, "asha").status_code == 200              # the app is no browser
    assert web(APIClient(HTTP_ORIGIN="http://testserver")).status_code == 200


def test_a_role_change_signs_the_app_out(api_as, make_user, login):
    """F-056: the app's tokens carry the old role."""
    from rest_framework.test import APIClient

    from apps.accounts.models import Device

    admin, _ = api_as("admin")
    u = make_user(username="ops1", role="ops")
    assert login(APIClient(), "ops1").status_code == 200
    assert Device.objects.filter(user=u, revoked_at__isnull=True).count() == 1
    assert admin.patch(f"/api/v1/users/{u.id}", {"name": "Ops One"},
                       format="json").status_code == 200
    assert Device.objects.filter(user=u, revoked_at__isnull=True).count() == 1   # no role change
    assert admin.patch(f"/api/v1/users/{u.id}", {"role": "expert"},
                       format="json").status_code == 200
    assert not Device.objects.filter(user=u, revoked_at__isnull=True).exists()
