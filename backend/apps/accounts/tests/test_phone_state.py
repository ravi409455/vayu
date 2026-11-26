"""F-243: the deactivate and sign-out warnings come from what the person's phone last reported."""
import pytest
from django.utils import timezone

from apps.accounts.models import Device, Role

pytestmark = pytest.mark.django_db


def test_the_phone_state_sums_what_signed_in_phones_still_hold(api_as, make_user):
    admin, _ = api_as(Role.ADMIN)
    target = make_user(Role.EXPERT)
    seen = timezone.now()
    Device.objects.create(user=target, unsynced={"drafts": 1, "files": 3}, last_seen_at=seen)
    Device.objects.create(user=target, unsynced={"drafts": 5, "files": 9}, revoked_at=seen)   # gone
    r = admin.get(f"/api/v1/users/{target.id}/phone")
    assert r.status_code == 200
    body = r.json()
    assert (body["devices"], body["drafts"], body["files"], body["unknown"]) == (1, 1, 3, False)
    assert body["last_seen_at"] is not None


def test_a_phone_that_never_reported_is_unknown_and_none_is_none(api_as, make_user):
    admin, _ = api_as(Role.ADMIN)
    target = make_user(Role.EXPERT)
    assert admin.get(f"/api/v1/users/{target.id}/phone").json() == {
        "devices": 0, "drafts": 0, "files": 0, "unknown": False, "signed_out_holding": 0,
        "last_seen_at": None}
    Device.objects.create(user=target)                               # unsynced is null
    body = admin.get(f"/api/v1/users/{target.id}/phone").json()
    assert body["devices"] == 1 and body["unknown"] is True


@pytest.mark.parametrize("role, status", [(Role.OPS, 403), (Role.EXPERT, 403)])
def test_only_people_who_may_deactivate_or_sign_out_see_it(api_as, make_user, role, status):
    client, _ = api_as(role)
    target = make_user(Role.EXPERT)
    assert client.get(f"/api/v1/users/{target.id}/phone").status_code == status
