import pytest
from apps.bookings.models import Booking, Inspection
from apps.bookings.tests.conftest import env, booking, create  # noqa
from apps.bookings.tests.test_submissions import ienv, started, assign, start, submit, GOOD  # noqa
from apps.media.tests.conftest import s3  # noqa

pytestmark = pytest.mark.django_db


def test_force_release_then_same_expert_restarts(started):
    env, b, s = started
    first = s["inspection"]["id"]
    assert env.ops.post(f"/api/v1/bookings/{b['id']}/force-release").status_code == 200
    r = start(env.expert, b)
    second = r.json()["inspection"]["id"]
    r2 = submit(env.expert, b)
    rows = list(Inspection.objects.filter(booking_id=b["id"]).order_by("created_at").values_list("id", "status"))
    print("RESTART", r.status_code, first == second, r2.status_code,
          [(str(i) == first, st) for i, st in rows], Booking.objects.get(pk=b["id"]).conflict)
