"""Each inspection form says which roles may see its submissions; a role left out sees nothing."""
import pytest

from apps.bookings.models import Booking
from apps.media.tests.conftest import jpeg, s3, upload  # noqa: F401
from apps.reports.tests.test_reports import renv  # noqa: F401

from .test_search_dashboards import many  # noqa: F401
from .test_submissions import GOOD, assign, ienv, start, submit  # noqa: F401

pytestmark = pytest.mark.django_db


def hide_from(env, *roles):
    r = env.admin.patch(f"/api/v1/forms/{env.form_id}",
                        {"submission_roles": [x for x in ("expert", "ops") if x not in roles]},
                        format="json")
    assert r.status_code == 200, r.content


@pytest.fixture
def done(ienv, booking):
    assign(ienv, booking)
    start(ienv.expert, booking)
    assert submit(ienv.expert, booking).status_code == 200
    return ienv, booking


def test_by_default_expert_ops_and_admin_all_see_the_submission(done):
    env, b = done
    assert env.admin.get("/api/v1/forms").json()["results"][-1]["submission_roles"] in (
        ["expert", "ops"], [])
    for client in (env.admin, env.ops, env.expert):
        got = client.get(f"/api/v1/bookings/{b['id']}/inspections").json()
        assert len(got) == 1 and got[0]["answers"]["inspection"]["chassis_no"]


def test_a_role_left_off_the_list_sees_no_inspection_anywhere(done):
    env, b = done
    insp = env.admin.get(f"/api/v1/bookings/{b['id']}/inspections").json()[0]
    hide_from(env, "ops")
    assert env.ops.get(f"/api/v1/bookings/{b['id']}/inspections").json() == []
    assert env.ops.get(f"/api/v1/inspections/{insp['id']}").status_code == 404
    assert env.ops.patch(f"/api/v1/inspections/{insp['id']}", {"row_version": 0, "answers": {}},
                         format="json").status_code == 404
    assert env.ops.patch(f"/api/v1/inspections/{insp['id']}/overrides", {"row_version": 0},
                         format="json").status_code == 404
    assert env.expert.get(f"/api/v1/bookings/{b['id']}/inspections").json()      # others unaffected
    assert env.admin.get(f"/api/v1/inspections/{insp['id']}").status_code == 200   # Admin always


def test_the_chassis_number_of_a_hidden_form_cannot_be_searched(done):
    env, b = done
    assert env.ops.get("/api/v1/bookings?search=273129").json()["count"] == 1
    hide_from(env, "ops")
    assert env.ops.get("/api/v1/bookings?search=273129").json()["count"] == 0
    assert env.admin.get("/api/v1/bookings?search=273129").json()["count"] == 1


def test_a_switched_off_hidden_form_stays_hidden_from_search(done):
    from apps.forms.models import Form

    env, b = done
    hide_from(env, "ops")
    Form.objects.filter(type="custom").update(is_active=False)         # hiding must not depend on it being live
    assert env.ops.get("/api/v1/bookings?search=273129").json()["count"] == 0


def test_the_experts_own_submit_response_is_blank_when_the_expert_may_not_see_it(ienv, booking):
    assign(ienv, booking)
    start(ienv.expert, booking)
    hide_from(ienv, "expert")
    r = submit(ienv.expert, booking)
    assert r.status_code == 200                          # filling and submitting still work
    assert r.json()["inspection"]["answers"] == {} and r.json()["inspection"]["scores"] is None
    assert ienv.expert.get(f"/api/v1/bookings/{booking['id']}/inspections").json() == []


def test_the_report_of_a_hidden_submission_is_not_reachable(renv, settings):
    from apps.reports.tests.test_reports import complete_job, set_template

    set_template(renv)
    b = complete_job(renv, settings=settings)
    url = f"/api/v1/bookings/{b['id']}/report"
    assert renv.ops.get(url).status_code == 200
    hide_from(renv, "ops")
    assert renv.ops.get(url).status_code == 404            # the report is the submission
    assert renv.ops.post(url + "/regenerate").status_code == 404
    assert renv.admin.get(url).status_code == 200


def test_photo_fields_of_a_hidden_form_are_hidden_for_that_role(ienv, booking, settings):
    from apps.forms.models import Field
    from apps.media.services import hidden_fields

    assign(ienv, booking)
    start(ienv.expert, booking)
    upload(ienv.expert, booking["id"], jpeg(), settings, field_key="door_photo")
    b = Booking.objects.get(pk=booking["id"])
    assert "door_photo" not in hidden_fields(ienv.ops_user, b)
    hide_from(ienv, "ops")
    assert "door_photo" in hidden_fields(ienv.ops_user, b)
    assert Field.objects.filter(key="door_photo").exists() and GOOD


def test_only_inspection_forms_have_the_setting_and_it_is_validated(ienv):
    from apps.forms.models import Form

    booking_form = Form.objects.get(type="booking")
    r = ienv.admin.patch(f"/api/v1/forms/{booking_form.id}", {"submission_roles": ["ops"]},
                         format="json")
    assert r.status_code == 400
    for bad in ("ops", ["admin"], ["ops", "ops"], [1]):
        r = ienv.admin.patch(f"/api/v1/forms/{ienv.form_id}", {"submission_roles": bad},
                             format="json")
        assert r.status_code == 400, bad
    assert ienv.admin.patch(f"/api/v1/forms/{ienv.form_id}", {"submission_roles": []},
                            format="json").status_code == 200
    assert ienv.ops.patch(f"/api/v1/forms/{ienv.form_id}", {"submission_roles": ["ops"]},
                          format="json").status_code == 403


# ---------------------------------------------------------------- automatic date and time

def _with_auto_fields(ienv):
    from .test_submissions import publish_form

    d = ienv.admin.post(f"/api/v1/forms/{ienv.form_id}/drafts").json()["id"]
    sec = ienv.admin.get(f"/api/v1/form-versions/{d}").json()["pages"][0]["sections"][0]["id"]
    for key, type_ in (("arrived_at", "datetime"), ("arrived_date", "date"), ("arrived_time", "time")):
        r = ienv.admin.post(f"/api/v1/sections/{sec}/fields", {
            "key": key, "label": key, "type": type_, "config": {"auto": True}}, format="json")
        assert r.status_code == 201, r.content
    publish_form(ienv.admin, ienv.form_id)


def test_automatic_date_time_fields_the_phone_left_empty_get_the_servers_time(ienv, booking):
    from apps.bookings.models import Inspection

    _with_auto_fields(ienv)
    assign(ienv, booking)
    start(ienv.expert, booking)
    assert submit(ienv.expert, booking).status_code == 200
    got = Inspection.objects.get(booking_id=booking["id"]).answers["inspection"]
    assert got["arrived_date"].count("-") == 2 and ":" in got["arrived_time"]
    assert got["arrived_at"].startswith(got["arrived_date"])          # the same moment, in IST
    assert got["arrived_at"].endswith("+05:30")


def test_a_value_the_phone_did_send_is_kept(ienv, booking):
    from apps.bookings.models import Inspection

    _with_auto_fields(ienv)
    assign(ienv, booking)
    start(ienv.expert, booking)
    mine = {**GOOD["inspection"], "arrived_time": "09:15"}
    assert submit(ienv.expert, booking, {"inspection": mine}).status_code == 200
    assert Inspection.objects.get(booking_id=booking["id"]).answers["inspection"][
        "arrived_time"] == "09:15"
