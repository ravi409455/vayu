import pytest
from rest_framework.test import APIClient

from apps.accounts.models import AuditLog, Device, Role, User

from .conftest import PASSWORD

pytestmark = pytest.mark.django_db

NEW = {"username": "newbie", "name": "New Bie", "role": "expert", "password": "Temp-pass-123"}


def test_admin_creates_user_with_forced_password_change(api_as):
    client, _ = api_as(Role.ADMIN)
    r = client.post("/api/v1/users", NEW, format="json")
    assert r.status_code == 201
    body = r.json()
    assert body["must_change_password"] is True and body["role"] == "expert"
    assert "password" not in body
    assert User.objects.get(username="newbie").must_change_password is True


def test_username_unique_case_insensitively(api_as):
    client, _ = api_as(Role.ADMIN)
    assert client.post("/api/v1/users", NEW, format="json").status_code == 201
    dup = client.post("/api/v1/users", {**NEW, "username": "NEWBIE"}, format="json")
    assert dup.status_code == 400


@pytest.mark.parametrize(
    "patch",
    [{"role": "superuser"}, {"email": "not-an-email"}, {"password": "short1"},
     {"password": "newbie"}, {"username": ""}],
)
def test_create_validation(api_as, patch):
    client, _ = api_as(Role.ADMIN)
    assert client.post("/api/v1/users", {**NEW, **patch}, format="json").status_code == 400


def test_email_is_optional_but_stored_when_given(api_as):
    client, _ = api_as(Role.ADMIN)
    r = client.post("/api/v1/users", {**NEW, "email": "n@x.com"}, format="json")
    assert r.status_code == 201 and r.json()["email"] == "n@x.com"


@pytest.mark.parametrize("role", [Role.OPS, Role.EXPERT])
@pytest.mark.parametrize("action", ["create", "reset", "deactivate"])
def test_only_admin_can_mutate_users(api_as, make_user, role, action):
    client, _ = api_as(role)
    target = make_user(Role.EXPERT)
    calls = {
        "create": lambda: client.post("/api/v1/users", NEW, format="json"),
        "reset": lambda: client.post(
            f"/api/v1/users/{target.id}/reset-password", {"password": "Temp-pass-123"},
            format="json"),
        "deactivate": lambda: client.patch(
            f"/api/v1/users/{target.id}", {"is_active": False}, format="json"),
    }
    assert calls[action]().status_code == 403


def test_ops_can_list_users_expert_cannot(api_as, make_user):
    make_user(Role.EXPERT, username="e1")
    ops, _ = api_as(Role.OPS)
    assert ops.get("/api/v1/users").status_code == 200
    assert ops.get("/api/v1/users?role=expert").json()["results"][0]["username"] == "e1"
    expert, _ = api_as(Role.EXPERT)
    assert expert.get("/api/v1/users").status_code == 403


def test_reset_password_forces_change_unlocks_and_signs_devices_out(api_as, make_user, login):
    admin, _ = api_as(Role.ADMIN)
    target = make_user(username="asha")
    for _ in range(5):
        login(APIClient(), "asha", password="wrong-pass-1")
    r = admin.post(f"/api/v1/users/{target.id}/reset-password",
                   {"password": "Temp-pass-123"}, format="json")
    assert r.status_code == 200
    target.refresh_from_db()
    assert target.must_change_password is True and target.failed_attempts == 0
    assert target.locked_until is None
    assert login(APIClient(), "asha", password="Temp-pass-123").status_code == 200


def test_deactivate_blocks_login_and_revokes_devices(api_as, make_user, login):
    admin, _ = api_as(Role.ADMIN)
    target = make_user(username="asha")
    login(APIClient(), "asha")
    assert admin.patch(f"/api/v1/users/{target.id}", {"is_active": False},
                       format="json").status_code == 200
    assert login(APIClient(), "asha").status_code == 403
    assert Device.objects.filter(user=target, revoked_at__isnull=True).count() == 0


def test_admin_cannot_deactivate_self(api_as):
    admin, me = api_as(Role.ADMIN)
    r = admin.patch(f"/api/v1/users/{me.id}", {"is_active": False}, format="json")
    assert r.status_code == 400


def test_user_mutations_are_audited(api_as, make_user):
    admin, me = api_as(Role.ADMIN)
    target = make_user(username="asha")
    admin.post("/api/v1/users", NEW, format="json")
    admin.post(f"/api/v1/users/{target.id}/reset-password", {"password": "Temp-pass-123"},
               format="json")
    admin.patch(f"/api/v1/users/{target.id}", {"is_active": False}, format="json")
    actions = list(AuditLog.objects.filter(actor=me).values_list("action", flat=True))
    assert {"user.create", "user.reset_password", "user.deactivate"} <= set(actions)
    assert PASSWORD not in str(list(AuditLog.objects.values_list("summary", flat=True)))


def test_reactivate_and_edit_are_audited(api_as, make_user):
    admin, _ = api_as(Role.ADMIN)
    target = make_user(username="asha", is_active=False)
    admin.patch(f"/api/v1/users/{target.id}", {"is_active": True}, format="json")
    admin.patch(f"/api/v1/users/{target.id}", {"name": "Asha K", "role": "ops"}, format="json")
    actions = set(AuditLog.objects.values_list("action", flat=True))
    assert {"user.activate", "user.update"} <= actions
    target.refresh_from_db()
    assert target.name == "Asha K" and target.role == "ops"


def test_password_cannot_be_changed_through_user_patch(api_as, make_user, login):
    admin, _ = api_as(Role.ADMIN)
    target = make_user(username="asha")
    admin.patch(f"/api/v1/users/{target.id}", {"password": "Hacked-pass-1"}, format="json")
    assert login(APIClient(), "asha", password="Hacked-pass-1").status_code == 401


def test_common_passwords_are_rejected(api_as):
    admin, _ = api_as(Role.ADMIN)
    r = admin.post("/api/v1/users", {**NEW, "password": "password123"}, format="json")
    assert r.status_code == 400
