from unittest import mock

import pytest

from apps.bookings import submissions
from apps.bookings.tests.test_submissions import ienv, started  # noqa: F401
from apps.core.errors import CodedError

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("bad", [{"inspection": "x"}, {"ops": [1]}, "x", [1], 5])
def test_answers_must_be_objects(bad):
    with pytest.raises(CodedError) as e:
        submissions.check_shape(bad)
    assert e.value.detail == {"code": "INVALID_ANSWERS", "detail": mock.ANY}


@pytest.mark.parametrize("ok", [{}, {"inspection": {}}, {"inspection": None, "ops": {"a": 1}}])
def test_well_formed_answers_pass(ok):
    submissions.check_shape(ok)


def test_the_expert_filter_needs_a_user_id(env):
    assert env.ops.get("/api/v1/bookings?expert=abc").status_code == 400
    assert env.ops.get(f"/api/v1/bookings?expert={env.expert_user.id}").status_code == 200


def test_start_also_returns_the_check_in_form_for_the_wizard(ienv, booking):
    from apps.bookings.tests.test_submissions import assign, start

    assign(ienv, booking)
    r = start(ienv.expert, booking)
    assert r.json()["ops_form"] is None                       # no check-in form published yet
    form = ienv.admin.post("/api/v1/forms", {"key": "checkin", "kind": "ops", "name": "Check-in"},
                           format="json").json()
    v = form["draft_version"]["id"]
    sec = ienv.admin.get(f"/api/v1/form-versions/{v}").json()["pages"][0]["sections"][0]["id"]
    assert ienv.admin.post(f"/api/v1/sections/{sec}/fields", {
        "key": "paid", "label": "Paid", "type": "yes_no"}, format="json").status_code == 201
    rv = ienv.admin.get(f"/api/v1/form-versions/{v}").json()["row_version"]
    ienv.admin.post(f"/api/v1/form-versions/{v}/publish", {"row_version": rv}, format="json")
    from apps.bookings.models import Inspection

    # the same start request again (it is idempotent) now carries the form
    uuid_ = str(Inspection.objects.get(booking_id=booking["id"]).client_start_uuid)
    out = start(ienv.expert, booking, client_uuid=uuid_).json()
    keys = [f["key"] for p in out["ops_form"]["pages"] for s in p["sections"] for f in s["fields"]]
    assert "paid" in keys and "rating_config" not in out["ops_form"]


def test_a_booking_shows_its_conflict_and_alerts(env, booking):
    got = env.ops.get(f"/api/v1/bookings/{booking['id']}").json()
    assert got["conflict"] == "" and got["alerts"] == [] and got["withdrawn_expert"] is None


# ---------------------------------------------------------------- resolving "two experts"

@pytest.fixture
def conflict(started):
    """Expert A and expert B both submitted the same booking."""
    import uuid

    from rest_framework.test import APIClient

    from apps.bookings.models import Booking, Inspection
    from apps.bookings.tests.test_submissions import submit

    ienv, booking, _ = started
    b_user = ienv.make_user("expert", username="bee")
    Booking.objects.filter(pk=booking["id"]).update(assigned_expert=b_user)
    mine = Inspection.objects.get(booking_id=booking["id"])
    Inspection.objects.create(booking_id=booking["id"], expert=b_user, form_version=mine.form_version,
                              client_start_uuid=uuid.uuid4())
    assert submit(ienv.expert, booking).status_code == 200        # A: accepted, flagged
    other = APIClient()
    other.force_authenticate(user=b_user)
    assert submit(other, booking).status_code == 200              # B: also submitted
    assert Booking.objects.get(pk=booking["id"]).conflict == "TWO_EXPERTS"
    return ienv, booking, b_user


def test_ops_keep_one_inspection_and_the_other_is_set_aside_not_deleted(conflict):
    from apps.bookings.models import Booking, Inspection

    ienv, booking, b_user = conflict
    a_insp = Inspection.objects.get(booking_id=booking["id"], expert=ienv.expert_user)
    r = ienv.ops.post(f"/api/v1/bookings/{booking['id']}/resolve-conflict",
                      {"inspection": str(a_insp.id)}, format="json")
    assert r.status_code == 200 and r.json()["conflict"] == ""
    b = Booking.objects.get(pk=booking["id"])
    assert b.conflict == "" and b.assigned_expert_id == ienv.expert_user.id
    assert b.stage == "completed"                                   # no media: nothing to wait for
    assert Inspection.objects.get(booking_id=booking["id"], expert=b_user).status == "superseded"
    assert Inspection.objects.filter(booking_id=booking["id"]).count() == 2     # nothing deleted
    from apps.reports.context import latest_inspection

    latest = latest_inspection(b)
    assert latest is not None and latest.id == a_insp.id


def test_choosing_the_other_expert_hands_the_booking_to_them(conflict):
    from apps.bookings.models import Booking, Inspection

    ienv, booking, b_user = conflict
    b_insp = Inspection.objects.get(booking_id=booking["id"], expert=b_user)
    assert ienv.ops.post(f"/api/v1/bookings/{booking['id']}/resolve-conflict",
                         {"inspection": str(b_insp.id)}, format="json").status_code == 200
    b = Booking.objects.get(pk=booking["id"])
    assert b.assigned_expert_id == b_user.id and b.conflict == ""
    assert Inspection.objects.get(pk=b_insp.id).status == "submitted"


def test_resolve_conflict_refusals(conflict, started):
    ienv, booking, _ = conflict
    url = f"/api/v1/bookings/{booking['id']}/resolve-conflict"
    assert ienv.expert.post(url, {"inspection": "x"}, format="json").status_code == 403
    assert ienv.ops.post(url, {"inspection": "not-a-uuid"}, format="json").status_code in (400, 404)
    import uuid

    r = ienv.ops.post(url, {"inspection": str(uuid.uuid4())}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "INVALID_INSPECTION"
    from apps.bookings.models import Booking

    Booking.objects.filter(pk=booking["id"]).update(conflict="")
    r = ienv.ops.post(url, {"inspection": str(uuid.uuid4())}, format="json")
    assert r.status_code == 409 and r.json()["code"] == "NO_CONFLICT"


def test_resolving_a_booking_that_was_still_in_progress_moves_it_on(conflict):
    from apps.bookings.models import Booking, Inspection

    ienv, booking, _ = conflict
    Booking.objects.filter(pk=booking["id"]).update(stage="in_progress")
    keep = Inspection.objects.get(booking_id=booking["id"], expert=ienv.expert_user)
    assert ienv.ops.post(f"/api/v1/bookings/{booking['id']}/resolve-conflict",
                         {"inspection": str(keep.id)}, format="json").status_code == 200
    assert Booking.objects.get(pk=booking["id"]).stage == "completed"


def test_the_problem_queue_filters_conflicts_and_rejected_type_changes(conflict):
    from apps.bookings.models import Booking

    ienv, booking, _ = conflict
    ids = [b["id"] for b in ienv.ops.get("/api/v1/bookings?problem=conflict").json()["results"]]
    assert ids == [booking["id"]]
    assert ienv.ops.get("/api/v1/bookings?problem=type_change").json()["count"] == 0
    Booking.objects.filter(pk=booking["id"]).update(
        alerts=[{"code": "TYPE_CHANGE_REJECTED", "detail": "x", "at": "2026-01-01T00:00:00Z"}])
    assert ienv.ops.get("/api/v1/bookings?problem=type_change").json()["count"] == 1
    assert ienv.ops.get("/api/v1/bookings?problem=nope").status_code == 400
