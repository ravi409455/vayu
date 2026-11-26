"""A phone that signs out with unsent work keeps it (docs/plan-media-backup.md): the server keeps
that phone "holding work" after the sign-out, so another phone is still refused, while the same
install of the app may sign back in and send it. Admin sign-out, deactivating, a role change and
a password change release it, as before."""
import uuid

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Device, Role
from apps.core.testing import PASSWORD

pytestmark = pytest.mark.django_db

PHONE_A = str(uuid.uuid4())
PHONE_B = str(uuid.uuid4())


def bearer(token):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return c


def sign_in(login, username, install_id=PHONE_A):
    extra = {} if install_id is None else {"install_id": install_id}
    return login(APIClient(), username, **extra)


def sign_out(tokens, **counts):
    return bearer(tokens["access"]).post("/api/v1/auth/logout", counts or None, format="json")


def held(user):
    return Device.objects.filter(user=user, held_after_sign_out_at__isnull=False)


def test_sign_out_with_unsent_work_keeps_the_phone_holding_it(make_user, login):
    asha = make_user(username="asha")
    tokens = sign_in(login, "asha").json()
    assert sign_out(tokens, drafts=2, files=5).status_code == 204
    device = Device.objects.get(user=asha)
    assert device.revoked_at is not None and device.held_after_sign_out_at is not None
    assert device.unsynced == {"drafts": 2, "files": 5}
    assert bearer(tokens["access"]).get("/api/v1/auth/me").json()["code"] == "DEVICE_REVOKED"


def test_sign_out_with_nothing_unsent_holds_nothing(make_user, login):
    asha = make_user(username="asha")
    sign_out(sign_in(login, "asha").json(), drafts=0, files=0)
    assert not held(asha).exists()
    assert sign_in(login, "asha", PHONE_B).status_code == 200


def test_sign_out_without_counts_works_as_before(make_user, login):
    asha = make_user(username="asha")
    assert sign_out(sign_in(login, "asha").json()).status_code == 204
    assert not held(asha).exists() and Device.objects.get(user=asha).revoked_at is not None


@pytest.mark.parametrize("body", [{"drafts": -1, "files": 0}, {"drafts": "2", "files": 0},
                                  {"drafts": 1}, {"drafts": True, "files": 0}])
def test_sign_out_counts_are_checked(make_user, login, body):
    make_user(username="asha")
    r = sign_out(sign_in(login, "asha").json(), **body)
    assert r.status_code == 400 and r.json()["code"] == "INVALID_COUNTS"


def test_another_phone_is_refused_while_a_signed_out_phone_holds_work(make_user, login):
    make_user(username="asha")
    sign_out(sign_in(login, "asha").json(), drafts=1, files=3)
    r = sign_in(login, "asha", PHONE_B)
    assert r.status_code == 409 and r.json()["code"] == "DEVICE_HAS_UNSYNCED_DATA"
    assert (r.json()["drafts"], r.json()["files"]) == (1, 3)


def test_an_app_that_sends_no_install_id_is_refused_too(make_user, login):
    make_user(username="asha")
    sign_out(sign_in(login, "asha").json(), drafts=1, files=0)
    assert sign_in(login, "asha", install_id=None).status_code == 409


def test_the_same_install_signs_back_in_and_takes_its_work_over(make_user, login, logged):
    asha = make_user(username="asha")
    sign_out(sign_in(login, "asha").json(), drafts=1, files=3)
    r = sign_in(login, "asha", PHONE_A)
    assert r.status_code == 200
    assert not held(asha).exists()
    assert Device.objects.filter(user=asha, revoked_at__isnull=True).count() == 1
    assert logged("auth.device_taken_over")[0]["user_id"] == asha.pk


def test_a_sign_out_without_signal_is_taken_over_by_the_same_install(make_user, login):
    """The server never heard the sign-out: the old device still looks signed in with work."""
    asha = make_user(username="asha")
    old = sign_in(login, "asha").json()
    bearer(old["access"]).post("/api/v1/devices/heartbeat", {"drafts": 1, "files": 2},
                               format="json")
    assert sign_in(login, "asha", PHONE_B).status_code == 409             # another phone: no
    assert sign_in(login, "asha", PHONE_A).status_code == 200             # the same install: yes
    assert bearer(old["access"]).get("/api/v1/auth/me").json()["code"] == "DEVICE_REVOKED"
    assert Device.objects.filter(user=asha, revoked_at__isnull=True).count() == 1


def test_the_same_install_does_not_unlock_another_person(make_user, login):
    make_user(username="ravi")
    meera = make_user(username="meera")
    sign_out(sign_in(login, "ravi").json(), drafts=1, files=1)
    assert sign_in(login, "meera", PHONE_A).status_code == 200            # her own account
    assert sign_in(login, "ravi", PHONE_B).status_code == 409              # ravi's work still waits
    assert Device.objects.filter(user=meera, held_after_sign_out_at__isnull=False).count() == 0


def test_a_bad_install_id_is_refused(make_user, login):
    make_user(username="asha")
    r = sign_in(login, "asha", "not-a-uuid")
    assert r.status_code == 400 and "install_id" in str(r.json())
    assert not Device.objects.exists()


def test_the_install_id_is_never_sent_back_or_logged(make_user, login, api_as, logged, caplog):
    asha = make_user(username="asha")
    r = sign_in(login, "asha")
    sign_out(r.json(), drafts=1, files=1)
    admin, _ = api_as(Role.ADMIN)
    phone = admin.get(f"/api/v1/users/{asha.id}/phone")
    seen = r.content.decode() + phone.content.decode() + caplog.text + str(logged())
    assert PHONE_A not in seen


def test_sign_out_holding_work_is_logged_with_counts_only(make_user, login, logged):
    asha = make_user(username="asha")
    sign_out(sign_in(login, "asha").json(), drafts=2, files=7)
    (event,) = logged("auth.signed_out_holding_work")
    assert (event["user_id"], event["drafts"], event["files"]) == (asha.pk, 2, 7)


def test_the_database_refuses_a_held_mark_on_a_signed_in_phone(make_user):
    from django.db import IntegrityError
    from django.utils import timezone

    with pytest.raises(IntegrityError):
        Device.objects.create(user=make_user(username="asha"),
                              held_after_sign_out_at=timezone.now())


# ------------------------------------------------ releases: "accept the loss", as before

def test_admin_sign_out_devices_releases_a_held_phone(make_user, login, api_as):
    asha = make_user(username="asha")
    sign_out(sign_in(login, "asha").json(), drafts=1, files=0)
    admin, _ = api_as(Role.ADMIN)
    r = admin.post(f"/api/v1/users/{asha.id}/sign-out-devices")
    assert r.status_code == 200 and r.json()["revoked"] == 1
    assert not held(asha).exists()
    assert sign_in(login, "asha", PHONE_B).status_code == 200


@pytest.mark.parametrize("change", [{"is_active": False}, {"role": Role.OPS}])
def test_deactivating_or_a_role_change_releases_a_held_phone(make_user, login, api_as, change):
    asha = make_user(username="asha")
    sign_out(sign_in(login, "asha").json(), drafts=1, files=0)
    admin, _ = api_as(Role.ADMIN)
    assert admin.patch(f"/api/v1/users/{asha.id}", change, format="json").status_code == 200
    assert not held(asha).exists()


def test_an_admin_password_reset_releases_a_held_phone(make_user, login, api_as):
    asha = make_user(username="asha")
    sign_out(sign_in(login, "asha").json(), drafts=1, files=0)
    admin, _ = api_as(Role.ADMIN)
    assert admin.post(f"/api/v1/users/{asha.id}/reset-password",
                      {"password": "N3w-strong-pass"}, format="json").status_code == 200
    assert not held(asha).exists()


def test_changing_ones_own_password_releases_a_held_phone(make_user, login):
    asha = make_user(username="asha")
    sign_out(sign_in(login, "asha").json(), drafts=1, files=0)
    web = APIClient()
    web.post("/api/v1/auth/login", {"username": "asha", "password": PASSWORD, "client": "web"},
             format="json")
    r = web.post("/api/v1/auth/change-password",
                 {"old_password": PASSWORD, "new_password": "N3w-strong-pass"}, format="json")
    assert r.status_code == 200
    assert not held(asha).exists()


# ------------------------------------------------ what Admins see on the Users page

def test_the_phone_state_counts_a_signed_out_phone_that_holds_work(api_as, make_user, login):
    asha = make_user(username="asha")
    sign_out(sign_in(login, "asha").json(), drafts=2, files=5)
    admin, _ = api_as(Role.ADMIN)
    body = admin.get(f"/api/v1/users/{asha.id}/phone").json()
    assert (body["devices"], body["signed_out_holding"]) == (0, 1)
    assert (body["drafts"], body["files"], body["unknown"]) == (2, 5, False)
