from unittest import mock

import pytest

from apps.bookings import submissions
from apps.bookings.tests.test_submissions import ienv  # noqa: F401
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
