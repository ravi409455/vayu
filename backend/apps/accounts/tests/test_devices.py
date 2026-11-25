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
    heartbeat(first, drafts=0, files=0)                 # the old phone has nothing left to send
    second = login(APIClient(), "asha", device_name="new").json()
    assert bearer(second["access"]).get("/api/v1/auth/me").status_code == 200
    old = bearer(first["access"]).get("/api/v1/auth/me")
    assert old.status_code == 401 and old.json()["code"] == "DEVICE_REVOKED"
    refresh = APIClient().post("/api/v1/auth/refresh", {"refresh": first["refresh"]}, format="json")
    assert refresh.status_code == 401 and refresh.json()["code"] == "DEVICE_REVOKED"


def heartbeat(tokens, **counts):
    return bearer(tokens["access"]).post("/api/v1/devices/heartbeat", counts, format="json")


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
    if role == Role.OPS:                  # off by default for Ops (F-223): an Admin grants it
        from apps.accounts.models import RolePermission

        RolePermission.objects.create(role="ops", permission="users.sign_out_devices",
                                      scope="all")
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


def test_mobile_logout_revokes_only_that_device(make_user, login):
    user = make_user(username="asha")
    tokens = login(APIClient(), "asha").json()
    assert bearer(tokens["access"]).post("/api/v1/auth/logout").status_code == 204
    assert Device.objects.get(user=user).revoked_at is not None


def test_garbage_refresh_token_is_a_plain_401():
    r = APIClient().post("/api/v1/auth/refresh", {"refresh": "not.a.token"}, format="json")
    assert r.status_code == 401


def test_the_app_refuses_admins_and_registers_no_device(make_user, login):
    make_user(username="boss", role=Role.ADMIN)
    r = login(APIClient(), "boss", device_name="Pixel")
    assert r.status_code == 403 and r.json()["code"] == "ADMIN_USE_WEB"
    assert not Device.objects.exists()
    web = APIClient().post("/api/v1/auth/login", {"username": "boss", "password": "Str0ng-pass-1",
                                                  "client": "web"}, format="json")
    assert web.status_code == 200                                 # the web still works for Admins


def test_ops_may_sign_in_on_the_app(make_user, login):
    make_user(username="priya", role=Role.OPS)
    assert login(APIClient(), "priya").status_code == 200
    assert Device.objects.filter(user__username="priya").exists()


# ------------------------------------------------ heartbeat and the unsynced-data rule

def test_the_heartbeat_records_what_the_phone_still_holds(make_user, login, settings):
    settings.MIN_APP_VERSION = 7
    make_user(username="asha")
    tokens = login(APIClient(), "asha").json()
    r = heartbeat(tokens, drafts=1, files=12)
    assert r.status_code == 200 and r.json()["min_app_version"] == 7 and r.json()["server_time"]
    d = Device.objects.get(user__username="asha")
    assert d.unsynced == {"drafts": 1, "files": 12} and d.last_seen_at is not None


@pytest.mark.parametrize("body", [{"drafts": -1, "files": 0}, {"drafts": "x", "files": 0},
                                  {"files": 0}, {"drafts": True, "files": 0}])
def test_the_heartbeat_needs_two_counts(make_user, login, body):
    make_user(username="asha")
    r = heartbeat(login(APIClient(), "asha").json(), **body)
    assert r.status_code == 400 and r.json()["code"] == "INVALID_COUNTS"


def test_only_a_phone_sends_a_heartbeat(make_user):
    make_user(username="asha")
    web = APIClient()
    web.post("/api/v1/auth/login", {"username": "asha", "password": "Str0ng-pass-1",
                                    "client": "web"}, format="json")
    r = web.post("/api/v1/devices/heartbeat", {"drafts": 0, "files": 0}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "NOT_A_DEVICE"


def test_a_new_phone_is_refused_while_the_old_one_holds_unsent_work(make_user, login):
    make_user(username="asha")
    old = login(APIClient(), "asha").json()
    heartbeat(old, drafts=1, files=4)
    r = login(APIClient(), "asha")
    assert r.status_code == 409 and r.json()["code"] == "DEVICE_HAS_UNSYNCED_DATA"
    assert r.json()["drafts"] == 1 and r.json()["files"] == 4
    assert bearer(old["access"]).get("/api/v1/auth/me").status_code == 200   # old one still works
    assert Device.objects.filter(revoked_at__isnull=True).count() == 1


def test_a_phone_that_never_reported_counts_as_holding_work(make_user, login):
    make_user(username="asha")
    login(APIClient(), "asha")
    r = login(APIClient(), "asha")
    assert r.status_code == 409 and r.json()["drafts"] is None and r.json()["files"] is None


def test_signing_out_the_phones_lets_a_new_one_in(make_user, login, api_as):
    user = make_user(username="asha")
    heartbeat(login(APIClient(), "asha").json(), drafts=2, files=0)
    admin, _ = api_as(Role.ADMIN)
    assert admin.post(f"/api/v1/users/{user.id}/sign-out-devices").status_code == 200
    assert login(APIClient(), "asha").status_code == 200
