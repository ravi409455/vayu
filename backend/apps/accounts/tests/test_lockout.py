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
    fail(login, 5)
    r = login(APIClient(), "asha")
    # one answer for every failure (F-055): a lock never says the username exists
    assert r.status_code == 401 and r.json()["code"] == "INVALID_CREDENTIALS"


def test_the_lock_is_for_that_username_from_that_address_only(make_user, login):
    make_user(username="asha")
    make_user(username="ravi")
    fail(login, 5)
    assert login(APIClient(), "ravi").status_code == 200           # same address, other user
    other = APIClient(REMOTE_ADDR="10.0.0.9")                      # same user, other phone
    assert login(other, "asha").status_code == 200


def test_unknown_usernames_are_counted_the_same_way(db, login):
    for _ in range(6):
        r = login(APIClient(), "nobody", password="wrong-pass-1")
        assert r.status_code == 401 and r.json()["code"] == "INVALID_CREDENTIALS"


def test_lock_lasts_15_minutes(make_user, login):
    make_user(username="asha")
    with freeze_time("2026-01-01 10:00:00") as clock:
        fail(login, 4)
        login(APIClient(), "asha", password="wrong-pass-1")
        clock.tick(60 * 14)
        assert login(APIClient(), "asha").status_code == 401
        clock.tick(60 * 1 + 1)
        assert login(APIClient(), "asha").status_code == 200


def test_success_resets_the_counter(make_user, login):
    make_user(username="asha")
    fail(login, 4)
    assert login(APIClient(), "asha").status_code == 200
    Device.objects.update(unsynced={"drafts": 0, "files": 0})   # that phone has nothing pending
    fail(login, 4)
    assert login(APIClient(), "asha").status_code == 200
