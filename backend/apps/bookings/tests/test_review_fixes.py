from unittest import mock

import pytest

from apps.bookings import submissions
from apps.bookings.models import Booking
from apps.bookings.tests.test_submissions import ienv, started  # noqa: F401
from apps.core.errors import CodedError

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("bad", [{"inspection": "x"}, {"start": [1]}, {"end": "x"}, "x", [1], 5])
def test_answers_must_be_objects(bad):
    with pytest.raises(CodedError) as e:
        submissions.check_shape(bad)
    assert e.value.detail == {"code": "INVALID_ANSWERS", "detail": mock.ANY}


@pytest.mark.parametrize("ok", [{}, {"inspection": {}}, {"inspection": None, "start": {"a": 1}, "end": {}}])
def test_well_formed_answers_pass(ok):
    submissions.check_shape(ok)


def test_the_expert_filter_needs_a_user_id(env):
    assert env.ops.get("/api/v1/bookings?expert=abc").status_code == 400
    assert env.ops.get(f"/api/v1/bookings?expert={env.expert_user.id}").status_code == 200


def _publish_system(admin, ftype, field_key):
    from apps.forms.models import Form

    form = Form.objects.get(type=ftype)
    v = form.versions.get(status="draft").id
    sec = admin.get(f"/api/v1/form-versions/{v}").json()["pages"][0]["sections"][0]["id"]
    assert admin.post(f"/api/v1/sections/{sec}/fields", {
        "key": field_key, "label": field_key, "type": "yes_no"}, format="json").status_code == 201
    rv = admin.get(f"/api/v1/form-versions/{v}").json()["row_version"]
    assert admin.post(f"/api/v1/form-versions/{v}/publish", {"row_version": rv},
                      format="json").status_code == 200


def test_start_returns_the_start_and_end_forms_the_inspection_is_pinned_to(ienv, booking):
    from apps.bookings.models import Inspection
    from apps.bookings.tests.test_submissions import assign, start

    assign(ienv, booking)
    r = start(ienv.expert, booking)
    assert r.json()["start_form"] is None and r.json()["end_form"] is None    # nothing published
    Inspection.objects.all().delete()
    Booking.objects.filter(pk=booking["id"]).update(stage="assigned")
    _publish_system(ienv.admin, "start", "paid_start")
    _publish_system(ienv.admin, "end", "paid_end")
    out = start(ienv.expert, booking).json()
    for part, key in (("start_form", "paid_start"), ("end_form", "paid_end")):
        keys = [f["key"] for p in out[part]["pages"] for s in p["sections"] for f in s["fields"]]
        assert key in keys and "rating_config" not in out[part]
    insp = Inspection.objects.get(booking_id=booking["id"])
    assert insp.start_version_id and insp.end_version_id


def test_the_pinned_start_form_does_not_change_when_a_newer_one_is_published(ienv, booking):
    from apps.bookings.models import Inspection
    from apps.bookings.tests.test_submissions import assign, start

    _publish_system(ienv.admin, "start", "first_q")
    assign(ienv, booking)
    out = start(ienv.expert, booking).json()
    pinned = Inspection.objects.get(booking_id=booking["id"]).start_version_id
    from apps.forms.models import Form

    start_form = Form.objects.get(type="start")
    draft = ienv.admin.post(f"/api/v1/forms/{start_form.id}/drafts").json()["id"]
    sec = ienv.admin.get(f"/api/v1/form-versions/{draft}").json()["pages"][0]["sections"][0]["id"]
    ienv.admin.post(f"/api/v1/sections/{sec}/fields", {"key": "second_q", "label": "q",
                    "type": "yes_no"}, format="json")
    rv = ienv.admin.get(f"/api/v1/form-versions/{draft}").json()["row_version"]
    ienv.admin.post(f"/api/v1/form-versions/{draft}/publish", {"row_version": rv}, format="json")
    again = start(ienv.expert, booking, client_uuid=str(Inspection.objects.get(
        booking_id=booking["id"]).client_start_uuid)).json()          # idempotent restart
    keys = [f["key"] for p in again["start_form"]["pages"] for s in p["sections"]
            for f in s["fields"]]
    assert "second_q" not in keys and "first_q" in keys
    assert Inspection.objects.get(booking_id=booking["id"]).start_version_id == pinned
    assert out["start_form"] is not None


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


def test_resolving_needs_the_assign_permission_too(conflict):
    from apps.accounts.catalog import DEFAULTS
    from apps.bookings.models import Booking, Inspection

    ienv, booking, _ = conflict
    perms = {k: v for k, v in DEFAULTS["ops"].items() if k != "bookings.assign"}
    assert ienv.admin.put("/api/v1/roles/ops/permissions", {"permissions": perms},
                          format="json").status_code == 200
    keep = Inspection.objects.get(booking_id=booking["id"], expert=ienv.expert_user)
    r = ienv.ops.post(f"/api/v1/bookings/{booking['id']}/resolve-conflict",
                      {"inspection": str(keep.id)}, format="json")
    assert r.status_code == 403
    assert Booking.objects.get(pk=booking["id"]).conflict == "TWO_EXPERTS"        # untouched


def test_resolving_leaves_other_experts_drafts_alone(conflict):
    import uuid

    from apps.bookings.models import Inspection

    ienv, booking, b_user = conflict
    third = ienv.make_user("expert", username="cee")
    keep = Inspection.objects.get(booking_id=booking["id"], expert=ienv.expert_user)
    draft = Inspection.objects.create(booking_id=booking["id"], expert=third,
                                      form_version=keep.form_version, client_start_uuid=uuid.uuid4())
    assert ienv.ops.post(f"/api/v1/bookings/{booking['id']}/resolve-conflict",
                         {"inspection": str(keep.id)}, format="json").status_code == 200
    assert Inspection.objects.get(pk=draft.pk).status == "draft"                   # not set aside
