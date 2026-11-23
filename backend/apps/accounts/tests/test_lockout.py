import pytest
from freezegun import freeze_time
from rest_framework.test import APIClient

from apps.accounts.models import Device

pytestmark = pytest.mark.django_db


def fail(login, n, username="asha"):
    for _ in range(n):
        assert login(APIClient(), username, password="wrong-pass-1").status_code == 401


def test_four_failures_do_not_lock(make_user, login):
    make_user(username="asha")
    fail(login, 4)
    assert login(APIClient(), "asha").status_code == 200


def test_fifth_failure_locks_even_for_the_right_password(make_user, login):
    make_user(username="asha")
    fail(login, 4)
    assert login(APIClient(), "asha", password="wrong-pass-1").status_code == 403  # 5th locks
    r = login(APIClient(), "asha")
    assert r.status_code == 403 and r.json()["code"] == "ACCOUNT_LOCKED"


def test_lock_lasts_15_minutes(make_user, login):
    make_user(username="asha")
    with freeze_time("2026-01-01 10:00:00") as clock:
        fail(login, 4)
        login(APIClient(), "asha", password="wrong-pass-1")
        clock.tick(60 * 14)
        assert login(APIClient(), "asha").status_code == 403
        clock.tick(60 * 1 + 1)
        assert login(APIClient(), "asha").status_code == 200


def test_success_resets_the_counter(make_user, login):
    make_user(username="asha")
    fail(login, 4)
    assert login(APIClient(), "asha").status_code == 200
    Device.objects.update(unsynced={"drafts": 0, "files": 0})   # that phone has nothing pending
    fail(login, 4)
    assert login(APIClient(), "asha").status_code == 200
