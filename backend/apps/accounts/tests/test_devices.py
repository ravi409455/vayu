import pytest
from rest_framework.test import APIClient

from apps.accounts.models import AuditLog, Device, Role

pytestmark = pytest.mark.django_db


def bearer(token):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return c


def test_first_mobile_login_registers_a_device(make_user, login):
    user = make_user(username="asha")
    r = login(APIClient(), "asha", device_name="iQOO Z7s")
    d = Device.objects.get(user=user)
    assert str(d.id) == r.json()["device_id"] and d.name == "iQOO Z7s" and d.revoked_at is None


def test_new_device_login_revokes_the_old_one(make_user, login):
    make_user(username="asha")
    first = login(APIClient(), "asha", device_name="old").json()
    second = login(APIClient(), "asha", device_name="new").json()
    assert bearer(second["access"]).get("/api/v1/auth/me").status_code == 200
    old = bearer(first["access"]).get("/api/v1/auth/me")
    assert old.status_code == 401 and old.json()["code"] == "DEVICE_REVOKED"
    refresh = APIClient().post("/api/v1/auth/refresh", {"refresh": first["refresh"]}, format="json")
    assert refresh.status_code == 401 and refresh.json()["code"] == "DEVICE_REVOKED"


def test_devices_of_different_users_are_independent(make_user, login):
    make_user(username="asha")
    make_user(username="ravi")
    a = login(APIClient(), "asha").json()
    login(APIClient(), "ravi")
    assert bearer(a["access"]).get("/api/v1/auth/me").status_code == 200


def test_web_login_neither_creates_nor_revokes_devices(make_user, login):
    make_user(username="asha")
    mobile = login(APIClient(), "asha").json()
    web = APIClient()
    web.post("/api/v1/auth/login", {"username": "asha", "password": "Str0ng-pass-1",
                                    "client": "web"}, format="json")
    assert Device.objects.count() == 1
    assert bearer(mobile["access"]).get("/api/v1/auth/me").status_code == 200


def test_mobile_login_leaves_a_web_session_alone(make_user, login):
    make_user(username="asha")
    web = APIClient()
    web.post("/api/v1/auth/login", {"username": "asha", "password": "Str0ng-pass-1",
                                    "client": "web"}, format="json")
    login(APIClient(), "asha")
    assert web.get("/api/v1/auth/me").status_code == 200


@pytest.mark.parametrize("role", [Role.OPS, Role.ADMIN])
def test_ops_and_admin_can_sign_out_all_devices(api_as, make_user, login, role):
    client, actor = api_as(role)
    target = make_user(username="asha")
    tokens = login(APIClient(), "asha").json()
    r = client.post(f"/api/v1/users/{target.id}/sign-out-devices")
    assert r.status_code == 200 and "unsynced" in r.json()["warning"].lower()
    assert bearer(tokens["access"]).get("/api/v1/auth/me").json()["code"] == "DEVICE_REVOKED"
    row = AuditLog.objects.get(action="user.sign_out_devices")
    assert row.actor == actor and row.target_id == str(target.id)


def test_expert_cannot_force_sign_out(api_as, make_user):
    client, _ = api_as(Role.EXPERT)
    target = make_user(Role.EXPERT)
    assert client.post(f"/api/v1/users/{target.id}/sign-out-devices").status_code == 403
