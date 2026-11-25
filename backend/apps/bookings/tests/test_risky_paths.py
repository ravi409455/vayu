"""F-159: regression tests for risky paths the review found untested (no behaviour change)."""
import pytest

from apps.accounts.models import User
from apps.bookings.models import Booking

from .conftest import create
from .test_submissions import assign

pytestmark = pytest.mark.django_db


def _edit(env, b, **answers):
    rv = Booking.objects.get(pk=b["id"]).row_version
    return env.ops.patch(f"/api/v1/bookings/{b['id']}", {"answers": answers, "row_version": rv},
                         format="json")


def test_ops_can_still_edit_a_booking_whose_expert_was_deactivated(env):
    b = create(env.ops, booking_id="RP1").json()
    assign(env, b, env.expert_user)
    User.objects.filter(pk=env.expert_user.pk).update(is_active=False)
    r = _edit(env, b, customer_name="Asha K")
    assert r.status_code == 200, r.json()
    after = Booking.objects.get(pk=b["id"])
    assert after.answers["customer_name"] == "Asha K"
    assert after.assigned_expert_id == env.expert_user.pk          # kept, not silently dropped
