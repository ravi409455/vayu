"""F-222: the phone says when its clock was not checked; the server keeps it (true wins) and Ops
see it in the problem list and on the booking."""
import uuid

import pytest

from apps.bookings.models import Booking, Inspection
from apps.bookings.tests.test_submissions import GOOD, assign, ienv, start, submit  # noqa: F401
from apps.media.tests.conftest import s3  # noqa: F401

pytestmark = pytest.mark.django_db


def test_an_unchecked_clock_at_start_is_kept_and_shown_to_ops(ienv, booking):
    assign(ienv, booking)
    r = start(ienv.expert, booking, unverified_time=True)
    assert r.status_code == 200 and r.json()["inspection"]["unverified_time"] is True
    assert r.json()["booking"]["unverified_time"] is True
    # later sends say false: true wins
    assert submit(ienv.expert, booking, unverified_time=False).status_code == 200
    assert Inspection.objects.get(booking_id=booking["id"]).unverified_time is True
    ids = [b["id"] for b in ienv.ops.get("/api/v1/bookings?problem=unverified_time")
           .json()["results"]]
    assert ids == [booking["id"]]


def test_a_submit_alone_or_any_later_submit_can_flag_it(ienv, booking):
    from .conftest import create

    assign(ienv, booking)
    assert start(ienv.expert, booking).status_code == 200
    assert Booking.objects.get(pk=booking["id"]).unverified_time is False
    assert submit(ienv.expert, booking, unverified_time=True).status_code == 200
    assert Booking.objects.get(pk=booking["id"]).unverified_time is True
    other = create(ienv.ops, booking_id="UV2").json()
    assign(ienv, other)
    v = Inspection.objects.get(booking_id=booking["id"]).form_version_id
    r = ienv.expert.post(f"/api/v1/bookings/{other['id']}/submit", {
        "client_submission_uuid": str(uuid.uuid4()), "answers": GOOD, "form_version": v,
        "unverified_time": True}, format="json")
    assert r.status_code == 200 and r.json()["inspection"]["unverified_time"] is True


def test_no_flag_no_problem(ienv, booking):
    assign(ienv, booking)
    start(ienv.expert, booking, unverified_time="yes")         # only a real true counts
    submit(ienv.expert, booking)
    assert ienv.ops.get("/api/v1/bookings?problem=unverified_time").json()["count"] == 0
