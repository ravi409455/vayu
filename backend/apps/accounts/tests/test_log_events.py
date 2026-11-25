"""Q4.3: sign-in, device and password events are logged, with ids and reasons only."""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role
from apps.core.testing import PASSWORD

pytestmark = pytest.mark.django_db


def test_sign_in_success_failure_and_lockout_never_log_the_typed_username(make_user, login,
                                                                           logged, caplog):
    asha = make_user(username="asha")
    assert login(APIClient(), "asha").status_code == 200
    assert login(APIClient(), "nobody-typo", password="wrong-pass-1").status_code == 401
    for _ in range(5):
        login(APIClient(), "asha", password="wrong-pass-1")
    assert login(APIClient(), "asha").status_code == 401

    assert logged("auth.sign_in")[0]["user_id"] == asha.pk
    failed = logged("auth.sign_in_failed")
    assert failed[0]["user_id"] == "unknown user" and failed[0]["reason"] == "no_user"
    assert failed[1]["user_id"] == asha.pk and failed[1]["reason"] == "bad_password"
    assert "ip" in failed[0]
    assert logged("auth.locked_out")[0]["user_id"] == asha.pk
    assert logged("auth.sign_in_locked")[0]["user_id"] == asha.pk
    text = caplog.text + " ".join(str(f) for _, f in logged())
    assert "nobody-typo" not in text and "wrong-pass-1" not in text


def test_device_registered_revoked_and_password_changed(make_user, login, logged):
    user = make_user(Role.EXPERT)
    tokens = login(APIClient(), user.username).json()
    assert logged("auth.device_registered")[0]["device"] == tokens["device_id"]
    phone = APIClient()
    phone.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    r = phone.post("/api/v1/auth/change-password",
                   {"old_password": PASSWORD, "new_password": "An0ther-pass-9"}, format="json")
    assert r.status_code == 200
    row = logged("auth.password_changed")[0]
    assert (row["user_id"], row["changed_by"]) == (user.pk, user.pk) and row["request_id"] != "-"
    assert phone.post("/api/v1/auth/logout").status_code == 204
    assert logged("auth.device_revoked")[-1]["user_id"] == user.pk


def test_a_refused_permission_names_the_view_and_the_permission(api_as, logged):
    expert, user = api_as(Role.EXPERT)
    assert expert.get("/api/v1/integrations").status_code == 403
    row = logged("permission.refused")[-1]
    assert row["user_id"] == user.pk and row["view"] == "IntegrationList"
    assert row["permission"] == ["integrations.manage"]
