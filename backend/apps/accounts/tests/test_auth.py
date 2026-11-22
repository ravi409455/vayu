import pytest
from freezegun import freeze_time
from rest_framework.test import APIClient

from apps.accounts.models import Device, Role

from .conftest import PASSWORD

pytestmark = pytest.mark.django_db


def test_mobile_login_returns_tokens_flag_and_device(make_user, login):
    make_user(username="asha")
    r = login(APIClient(), "asha")
    assert r.status_code == 200
    body = r.json()
    assert body["access"] and body["refresh"] and body["device_id"]
    assert body["must_change_password"] is False


def test_login_is_case_insensitive_on_username(make_user, login):
    make_user(username="asha")
    assert login(APIClient(), "ASHA").status_code == 200


def test_login_reports_must_change_password(make_user, login):
    make_user(username="new1", must_change_password=True)
    assert login(APIClient(), "new1").json()["must_change_password"] is True


def test_wrong_password_and_unknown_user_look_identical(make_user, login):
    make_user(username="asha")
    wrong = login(APIClient(), "asha", password="nope-nope-1")
    unknown = login(APIClient(), "ghost", password="nope-nope-1")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.json()["code"] == "INVALID_CREDENTIALS"


@pytest.mark.parametrize("password", [PASSWORD, "wrong-pass-1"])
def test_inactive_user_gets_same_403_whatever_the_password(make_user, login, password):
    make_user(username="gone", is_active=False)
    r = login(APIClient(), "gone", password=password)
    assert r.status_code == 403
    assert r.json()["code"] == "ACCOUNT_DISABLED"


def test_forced_password_change_blocks_everything_else(make_user, login):
    make_user(Role.OPS, username="opsy", must_change_password=True)
    client = APIClient()
    token = login(client, "opsy").json()["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    blocked = client.get("/api/v1/users")
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "PASSWORD_CHANGE_REQUIRED"
    assert client.get("/api/v1/auth/me").status_code == 200


def test_change_password_clears_flag_and_replaces_password(make_user, login):
    make_user(username="asha", must_change_password=True)
    client = APIClient()
    token = login(client, "asha").json()["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    r = client.post(
        "/api/v1/auth/change-password",
        {"old_password": PASSWORD, "new_password": "Brand-new-pw-9"},
        format="json",
    )
    assert r.status_code == 200
    assert login(APIClient(), "asha", password=PASSWORD).status_code == 401
    ok = login(APIClient(), "asha", password="Brand-new-pw-9")
    assert ok.status_code == 200 and ok.json()["must_change_password"] is False


def test_change_password_rejects_wrong_old_password(make_user, api_as):
    client, _ = api_as(Role.EXPERT)
    r = client.post(
        "/api/v1/auth/change-password",
        {"old_password": "not-it-123", "new_password": "Brand-new-pw-9"},
        format="json",
    )
    assert r.status_code == 400


@pytest.mark.parametrize("bad", ["short1", "ASHA", "asha"])
def test_password_policy_enforced_on_change(make_user, login, bad):
    make_user(username="asha")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login(client, 'asha').json()['access']}")
    r = client.post(
        "/api/v1/auth/change-password",
        {"old_password": PASSWORD, "new_password": bad},
        format="json",
    )
    assert r.status_code == 400


def test_web_login_uses_a_session_and_no_device(make_user, login):
    make_user(username="webby", role=Role.OPS)
    client = APIClient()
    r = client.post(
        "/api/v1/auth/login",
        {"username": "webby", "password": PASSWORD, "client": "web"},
        format="json",
    )
    assert r.status_code == 200 and "access" not in r.json()
    assert client.get("/api/v1/auth/me").json()["username"] == "webby"
    assert Device.objects.count() == 0


def test_web_session_expires_after_inactivity(make_user):
    make_user(username="webby")
    client = APIClient()
    with freeze_time("2026-01-01 09:00:00") as clock:
        client.post(
            "/api/v1/auth/login",
            {"username": "webby", "password": PASSWORD, "client": "web"},
            format="json",
        )
        assert client.get("/api/v1/auth/me").status_code == 200
        clock.tick(60 * 60 * 9)  # 9h idle > 8h limit
        assert client.get("/api/v1/auth/me").status_code == 401


def test_web_logout_ends_session(make_user):
    make_user(username="webby")
    client = APIClient()
    client.post(
        "/api/v1/auth/login",
        {"username": "webby", "password": PASSWORD, "client": "web"},
        format="json",
    )
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_mobile_session_survives_long_offline_via_refresh(make_user, login):
    make_user(username="asha")
    client = APIClient()
    with freeze_time("2026-01-01") as clock:
        tokens = login(client, "asha").json()
        clock.tick(60 * 60 * 24 * 30)  # 30 days later: access expired, refresh alive
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        assert client.get("/api/v1/auth/me").status_code == 401
        r = APIClient().post("/api/v1/auth/refresh", {"refresh": tokens["refresh"]}, format="json")
        assert r.status_code == 200 and r.json()["access"]
