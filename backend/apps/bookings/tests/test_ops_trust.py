"""Plan batch 4 (backend): Ops can trust the screens.

H-07 / F-100: an edit accepts an unchanged stored value whose only problem is that its option was
archived or its user deactivated; everything else is still checked.
"""
import pytest

from apps.accounts.models import Role, User
from apps.bookings.models import Booking
from apps.forms.models import MasterListItem

from .conftest import create

pytestmark = pytest.mark.django_db


def _edit(env, b, **answers):
    rv = Booking.objects.get(pk=b["id"]).row_version
    return env.ops.patch(f"/api/v1/bookings/{b['id']}", {"answers": answers, "row_version": rv},
                         format="json")


def test_an_edit_keeps_a_lead_owner_who_left(env):
    owner = env.make_user(Role.OPS, username="leaver")
    b = create(env.ops, booking_id="P1", lead_owner=owner.id).json()
    User.objects.filter(pk=owner.pk).update(is_active=False)
    r = _edit(env, b, customer_name="Asha K")
    assert r.status_code == 200, r.json()
    assert Booking.objects.get(pk=b["id"]).answers["lead_owner"] == owner.id
    again = _edit(env, b, lead_owner=owner.id + 999)          # a new value is still checked
    assert again.status_code == 400 and again.json()["errors"] == {"lead_owner": "INVALID_USER"}


def test_an_edit_keeps_an_archived_city_but_not_a_new_archived_one(env):
    MasterListItem.objects.create(list=MasterListItem.objects.get(key="delhi").list,
                                  key="pune", label="Pune", archived=True)
    b = create(env.ops, booking_id="P2").json()
    MasterListItem.objects.filter(key="delhi").update(archived=True)
    assert _edit(env, b, customer_name="Asha K").status_code == 200
    r = _edit(env, b, city="pune")
    assert r.status_code == 400 and r.json()["errors"] == {"city": "ARCHIVED_OPTION"}
    still = _edit(env, b, city="nowhere")
    assert still.status_code == 400 and still.json()["errors"] == {"city": "INVALID_OPTION"}


# ---------------------------------------------------------------- events (H-13, F-142, F-239)

from apps.bookings.tests.test_review_fixes import _checkin, _publish_system  # noqa: E402
from apps.bookings.tests.test_submissions import GOOD, assign, ienv, start, started, submit  # noqa: E402,F401
from apps.core import events  # noqa: E402
from apps.media.tests.conftest import s3  # noqa: E402,F401


def test_reaching_completed_is_a_booking_update_before_the_completion(started):
    env, booking, _ = started
    with events.capture() as seen:
        assert submit(env.expert, booking).status_code == 200
    names = [n for n, _ in seen]
    done = [p for n, p in seen if n == "booking.updated"
            and p["changes"] == {"stage": ["submitted", "completed"]}]
    assert len(done) == 1 and names.index("inspection.completed") > names.index(
        "booking.updated", names.index("inspection.submitted"))


def test_assigning_the_same_expert_again_changes_nothing(env, booking):
    from apps.bookings.models import BookingActivity
    from apps.notify.models import Notification

    assign(env, booking)
    rows = BookingActivity.objects.count()
    with events.capture() as seen:
        assign(env, booking)
    assert seen == [] and BookingActivity.objects.count() == rows
    assert Notification.objects.filter(user=env.expert_user, title__startswith="New lead").count() == 1


def test_a_rejected_type_change_is_told_with_the_type_the_expert_started(ienv, booking):
    assign(ienv, booking)
    Booking.objects.filter(pk=booking["id"]).update(inspection_type="used_car")
    b = Booking.objects.get(pk=booking["id"])
    b.answers = {**b.answers, "inspection_type": "used_car"}
    b.save()
    seen_type = []

    def watch(name, payload):
        if name == "alert.type_change_rejected":
            seen_type.append(Booking.objects.get(pk=payload["booking"]).inspection_type)

    events.subscribe(watch)
    try:
        assert start(ienv.expert, booking, inspection_type="pdi").status_code == 200
    finally:
        events._subscribers.remove(watch)
    assert seen_type == ["pdi"]                   # the PDI form's integrations hear it


# ---------------------------------------------------------------- F-221 alerts can be cleared

def test_ops_clear_a_rejected_type_change_alert(env, booking):
    Booking.objects.filter(pk=booking["id"]).update(alerts=[
        {"code": "TYPE_CHANGE_REJECTED", "detail": "x", "at": "2026-01-01T00:00:00Z"},
        {"code": "LATE_WORK", "detail": "y", "at": "2026-01-01T00:00:00Z"}])
    url = f"/api/v1/bookings/{booking['id']}/clear-alert"
    assert env.ops.get("/api/v1/bookings?problem=type_change").json()["count"] == 1
    assert env.expert.post(url, {"code": "TYPE_CHANGE_REJECTED"}, format="json").status_code in (
        403, 404)
    r = env.ops.post(url, {"code": "TYPE_CHANGE_REJECTED"}, format="json")
    assert r.status_code == 200
    assert [a["code"] for a in Booking.objects.get(pk=booking["id"]).alerts] == ["LATE_WORK"]
    assert env.ops.get("/api/v1/bookings?problem=type_change").json()["count"] == 0
    again = env.ops.post(url, {"code": "TYPE_CHANGE_REJECTED"}, format="json")
    assert again.status_code == 409 and again.json()["code"] == "NO_ALERT"
    row = env.ops.get(f"/api/v1/bookings/{booking['id']}/activity").json()[0]
    assert row["kind"] == "alert_cleared" and row["changes"] == {
        "alert": ["TYPE_CHANGE_REJECTED", None]}


# ---------------------------------------------------------------- F-237, F-238, F-241

def test_experts_never_see_ops_review_activity(started):
    from apps.bookings.models import BookingActivity, Inspection

    env, booking, _ = started
    submit(env.expert, booking)
    insp = Inspection.objects.get(status="submitted")
    for kind in ("ratings_changed", "key_checks_changed", "alert_cleared"):
        BookingActivity.objects.create(booking_id=booking["id"], actor=env.ops_user, kind=kind,
                                       inspection=insp)
    kinds = {r["kind"] for r in env.expert.get(f"/api/v1/bookings/{booking['id']}/activity").json()}
    assert not kinds & {"ratings_changed", "key_checks_changed", "alert_cleared"}
    ops = {r["kind"] for r in env.ops.get(f"/api/v1/bookings/{booking['id']}/activity").json()}
    assert {"ratings_changed", "key_checks_changed"} <= ops


def test_no_rating_overrides_before_the_expert_submits(started):
    env, booking, s = started
    r = env.ops.patch(f"/api/v1/inspections/{s['inspection']['id']}/overrides",
                      {"ratings": {"engine": 1}, "row_version": 0}, format="json")
    assert r.status_code == 409 and r.json()["code"] == "NOT_SUBMITTED"


def test_the_check_in_is_kept_at_start_and_submitted_with_the_inspection(ienv, booking,
                                                                         settings):
    from apps.bookings.models import Inspection

    _publish_system(ienv.admin, "start", "arrived")
    assign(ienv, booking)
    body = _checkin(ienv, booking, settings)
    assert start(ienv.expert, booking, **body).status_code == 200
    insp = Inspection.objects.get(booking_id=booking["id"])
    assert insp.answers["start"]["selfie"] == body["start_answers"]["selfie"]  # Ops can see it
    assert submit(ienv.expert, booking).status_code == 200                     # no start part
    insp.refresh_from_db()
    assert insp.answers["start"]["selfie"] == body["start_answers"]["selfie"]


# ---------------------------------------------------------------- F-085 counts

def test_the_count_endpoint_counts_with_the_lists_filters_and_scope(env):
    a = create(env.ops, booking_id="C1").json()
    create(env.ops, booking_id="C2")
    assign(env, a)
    assert env.ops.get("/api/v1/bookings/count").json() == {"count": 2}
    assert env.ops.get("/api/v1/bookings/count", {"stage": "assigned"}).json() == {"count": 1}
    assert env.ops.get("/api/v1/bookings/count", {"search": "C2"}).json() == {"count": 1}
    assert env.expert.get("/api/v1/bookings/count").json() == {"count": 1}       # own only
    assert env.ops.get("/api/v1/bookings/count", {"date_from": "x"}).status_code == 400
