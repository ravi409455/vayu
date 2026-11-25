"""Q4.3 / Q4.4: booking and submission events are logged with ids, stages and codes only, and a
whole journey writes none of the customer's details into any log line."""
import logging

import pytest

from apps.core import log
from apps.media.tests.conftest import s3  # noqa: F401  (in-memory S3 for the selfie)

from .conftest import BASE, create
from .test_submissions import assign, ienv, start, submit  # noqa: F401  (fixture)

pytestmark = pytest.mark.django_db


def test_a_booking_journey_logs_each_step_and_no_personal_data(ienv, logged, caplog):  # noqa: F811
    caplog.set_level(logging.DEBUG)                     # every logger, every level
    b = create(ienv.ops).json()
    assign(ienv, b)
    assert start(ienv.expert, b).status_code == 200
    bad = submit(ienv.expert, b, answers={"inspection": {"door": "scratch"}})
    assert bad.status_code == 400
    assert submit(ienv.expert, b).status_code == 200
    other = create(ienv.ops, booking_id="SA11111").json()
    assert ienv.ops.post(f"/api/v1/bookings/{other['id']}/cancel", {"reason": "on_arrival"},
                         format="json").status_code == 200

    created = logged("booking.created")[0]
    assert (created["booking"], created["booking_id"]) == (b["id"], "SA37926")
    assert logged("booking.assigned")[0]["expert_id"] == ienv.expert_user.pk
    stages = [(r["from_stage"], r["to_stage"]) for r in logged("booking.stage_changed")]
    assert ("draft", "assigned") in stages and ("in_progress", "submitted") in stages
    rejected = logged("submission.rejected")[0]
    assert rejected["code"] == "INVALID_ANSWERS" and "INVALID_OPTION" in rejected["errors"]
    assert logged("submission.accepted")[0]["booking"] == b["id"]
    assert logged("booking.cancelled")[0]["booking_id"] == "SA11111"

    text = caplog.text + " ".join(str(r.__dict__) for r in caplog.records)
    for personal in (BASE["customer_name"], "9876543210", BASE["address"], "scratch"):
        assert personal not in text, personal


def test_a_conflict_is_logged_with_its_code(logged):
    log.on_domain_event("alert.conflict", {"booking": "u-1", "booking_id": "SA1",
                                           "code": "CONFLICT_TWO_EXPERTS"})
    assert logged("booking.conflict")[0]["code"] == "CONFLICT_TWO_EXPERTS"


def test_an_event_with_a_personal_field_name_is_a_bug():
    with pytest.raises(ValueError, match="must not log"):
        log.event("booking.created", phone="+91…")
