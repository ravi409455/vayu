"""Start / submit / offline conflicts / Ops edits of inspections."""
import uuid

import pytest
from rest_framework.exceptions import APIException

from apps.accounts.models import Role
from apps.bookings.models import Booking, Inspection
from apps.core import events

from .conftest import create

pytestmark = pytest.mark.django_db
OPTS = [{"key": "ok", "label": "Ok"},
        {"key": "dent", "label": "Dent", "is_defect": True, "severity": "major"}]


def publish_form(admin, form_id):
    v = admin.get(f"/api/v1/forms/{form_id}").json()["draft_version"]["id"]
    rv = admin.get(f"/api/v1/form-versions/{v}").json()["row_version"]
    assert admin.post(f"/api/v1/form-versions/{v}/publish", {"row_version": rv},
                      format="json").status_code == 200
    return v


@pytest.fixture
def ienv(env):
    """Published PDI inspection form (door choice, photo required if dent, odometer, rating)."""
    admin = env.admin
    form = admin.post("/api/v1/forms", {"key": "pdi", "kind": "inspection", "name": "PDI",
                                        "inspection_type": "pdi"}, format="json").json()
    v = form["draft_version"]["id"]
    sec = admin.get(f"/api/v1/form-versions/{v}").json()["pages"][0]["sections"][0]["id"]

    def add(key, type, **kw):
        r = admin.post(f"/api/v1/sections/{sec}/fields",
                       {"key": key, "label": key, "type": type, **kw}, format="json")
        assert r.status_code == 201, r.json()

    add("door", "single_choice", config={"options": OPTS}, required=True)
    add("door_photo", "photo", config={"max_count": 2},
        required_if={"==": [{"var": "inspection.door"}, "dent"]})
    add("odometer", "number", config={"min": 0})
    add("grade", "rating", config={"category": "engine"})
    publish_form(admin, form["id"])
    env.form_id = form["id"]
    return env


GOOD = {"inspection": {"chassis_no": "MA3YPKCSKTJ273129", "door": "ok", "odometer": 45}}


def assign(env, b, expert=None):
    expert = expert or env.expert_user
    env.ops.post(f"/api/v1/bookings/{b['id']}/assign", {"expert": expert.id}, format="json")


def start(client, b, **extra):
    body = {"client_uuid": str(uuid.uuid4()), "client_started_at": "2026-10-14T10:00:00+05:30",
            "inspection_type": "pdi", **extra}
    return client.post(f"/api/v1/bookings/{b['id']}/start", body, format="json")


def submit(client, b, answers=GOOD, **extra):
    body = {"client_submission_uuid": str(uuid.uuid4()), "answers": answers, **extra}
    return client.post(f"/api/v1/bookings/{b['id']}/submit", body, format="json")


@pytest.fixture
def started(ienv, booking):
    assign(ienv, booking)
    r = start(ienv.expert, booking)
    assert r.status_code == 200, r.json()
    return ienv, booking, r.json()


# ---------------------------------------------------------------- start

def test_start_moves_the_job_in_progress_pins_the_version_and_returns_the_form(ienv, booking):
    assign(ienv, booking)
    r = start(ienv.expert, booking)
    assert r.status_code == 200
    body = r.json()
    assert body["booking"]["stage"] == "in_progress" and body["booking"]["started_at"]
    assert body["inspection"]["status"] == "draft" and body["server_time"]
    keys = {f["key"] for p in body["form"]["pages"] for s in p["sections"] for f in s["fields"]}
    assert {"door", "odometer", "door_photo", "chassis_no"} <= keys
    assert "grade" not in keys  # system-filled: hidden from experts
    door = [f for p in body["form"]["pages"] for s in p["sections"] for f in s["fields"]
            if f["key"] == "door"][0]
    assert door["level"] == "edit"


def test_start_is_idempotent_by_client_uuid(ienv, booking):
    assign(ienv, booking)
    cid = str(uuid.uuid4())
    a = start(ienv.expert, booking, client_uuid=cid).json()
    b = start(ienv.expert, booking, client_uuid=cid)
    assert b.status_code == 200 and b.json()["inspection"]["id"] == a["inspection"]["id"]
    assert Inspection.objects.count() == 1


def test_only_the_assigned_expert_can_start(ienv, booking):
    assign(ienv, booking)
    other = ienv.make_user("expert", username="e2")
    from rest_framework.test import APIClient

    c = APIClient()
    c.force_authenticate(user=other)
    assert start(c, booking).status_code == 404
    assert start(ienv.ops, booking).status_code == 403  # ops lack submissions.fill


def test_start_needs_a_published_inspection_form_for_the_type(ienv, booking):
    assign(ienv, booking)
    ienv.ops.post(f"/api/v1/bookings/{booking['id']}/change-type", {"inspection_type": "ev"},
                  format="json")
    r = start(ienv.expert, booking, inspection_type="ev")
    assert r.status_code == 409 and r.json()["code"] == "NO_INSPECTION_FORM"


def test_the_form_version_stays_pinned_after_a_new_one_is_published(started):
    ienv, booking, body = started
    d = ienv.admin.post(f"/api/v1/forms/{ienv.form_id}/drafts").json()["id"]
    rv = ienv.admin.get(f"/api/v1/form-versions/{d}").json()["row_version"]
    ienv.admin.post(f"/api/v1/form-versions/{d}/publish", {"row_version": rv}, format="json")
    insp = Inspection.objects.get(pk=body["inspection"]["id"])
    assert insp.form_version.number == 1


def test_offline_type_change_by_ops_loses_to_the_experts_start(ienv, booking):
    assign(ienv, booking)
    ienv.ops.post(f"/api/v1/bookings/{booking['id']}/change-type", {"inspection_type": "ev"},
                  format="json")
    with events.capture() as seen:
        r = start(ienv.expert, booking, inspection_type="pdi")  # the expert started a PDI offline
    assert r.status_code == 200
    b = Booking.objects.get(pk=booking["id"])
    assert b.inspection_type == "pdi" and b.answers["inspection_type"] == "pdi"
    assert "alert.type_change_rejected" in [n for n, _ in seen]
    assert any(a["code"] == "TYPE_CHANGE_REJECTED" for a in b.alerts)


def test_below_the_minimum_app_version_cannot_start_but_can_submit(started, settings):
    ienv, booking, _ = started
    settings.MIN_APP_VERSION = 10
    ok = submit(ienv.expert, booking)
    assert ok.status_code == 200  # an inspection in progress can always be finished
    assign2 = create(ienv.ops, booking_id="SA2").json()
    assign(ienv, assign2)
    r = ienv.expert.post(f"/api/v1/bookings/{assign2['id']}/start",
                         {"client_uuid": str(uuid.uuid4()), "inspection_type": "pdi"},
                         format="json", HTTP_X_APP_VERSION="9")
    assert r.status_code == 426
    r = ienv.expert.post(f"/api/v1/bookings/{assign2['id']}/start",
                         {"client_uuid": str(uuid.uuid4()), "inspection_type": "pdi"},
                         format="json", HTTP_X_APP_VERSION="10")
    assert r.status_code == 200


# ---------------------------------------------------------------- submit

def test_submit_marks_submitted_and_is_idempotent(started):
    ienv, booking, _ = started
    sid = str(uuid.uuid4())
    r = submit(ienv.expert, booking, client_submission_uuid=sid)
    assert r.status_code == 200
    assert r.json()["booking"]["stage"] == "submitted" and r.json()["inspection"]["status"] == "submitted"
    assert r.json()["server_time"]
    again = submit(ienv.expert, booking, client_submission_uuid=sid)
    assert again.status_code == 200
    assert Inspection.objects.filter(status="submitted").count() == 1


def test_submit_revalidates_everything_on_the_server(started):
    ienv, booking, _ = started
    bad = {"inspection": {"chassis_no": "X", "door": "dent", "odometer": -3}}
    r = submit(ienv.expert, booking, bad)
    assert r.status_code == 400 and r.json()["code"] == "INVALID_ANSWERS"
    assert r.json()["errors"] == {"door_photo": "required", "odometer": "OUT_OF_RANGE"}
    assert Inspection.objects.get(status="draft")  # nothing was submitted


def test_experts_cannot_write_system_filled_or_unknown_fields(started):
    ienv, booking, _ = started
    r = submit(ienv.expert, booking, {"inspection": {**GOOD["inspection"], "grade": 5}})
    assert r.status_code == 403 and r.json()["code"] == "FIELD_ACCESS"
    r = submit(ienv.expert, booking, {"inspection": {**GOOD["inspection"], "ghost": 1}})
    assert r.status_code == 400 and r.json()["errors"] == {"ghost": "UNKNOWN_FIELD"}


def test_submit_needs_a_started_inspection(ienv, booking):
    assign(ienv, booking)
    r = submit(ienv.expert, booking)
    assert r.status_code == 409 and r.json()["code"] == "NOT_STARTED"


# ---------------------------------------------------------------- offline conflicts

def test_reassigned_to_b_who_has_not_started_a_wins_and_b_is_withdrawn(started):
    ienv, booking, _ = started
    b_user = ienv.make_user("expert", username="bee")
    Booking.objects.filter(pk=booking["id"]).update(stage="assigned", assigned_expert=b_user,
                                                    started_at=None)  # Ops force-released + reassigned
    r = submit(ienv.expert, booking)
    assert r.status_code == 200
    b = Booking.objects.get(pk=booking["id"])
    assert b.stage == "submitted" and b.assigned_expert_id == ienv.expert_user.id
    assert b.conflict == "TWO_EXPERTS" and b.withdrawn_expert_id == b_user.id


def test_reassigned_to_b_who_started_keeps_both_for_ops_to_choose(started):
    ienv, booking, _ = started
    b_user = ienv.make_user("expert", username="bee")
    Booking.objects.filter(pk=booking["id"]).update(assigned_expert=b_user)
    Inspection.objects.create(booking_id=booking["id"], expert=b_user,
                              form_version=Inspection.objects.get(booking_id=booking["id"]).form_version,
                              client_start_uuid=uuid.uuid4())
    r = submit(ienv.expert, booking)
    assert r.status_code == 200
    b = Booking.objects.get(pk=booking["id"])
    assert b.stage == "in_progress" and b.conflict == "TWO_EXPERTS"
    assert b.inspections.filter(status="submitted").count() == 1 and b.inspections.count() == 2


def test_a_cancelled_booking_still_accepts_the_experts_submission(started):
    ienv, booking, _ = started
    Booking.objects.filter(pk=booking["id"]).update(stage="cancelled")
    r = submit(ienv.expert, booking)
    assert r.status_code == 200
    b = Booking.objects.get(pk=booking["id"])
    assert b.stage == "cancelled" and b.inspections.filter(status="submitted").exists()


def test_a_force_released_draft_arriving_late_is_accepted_and_flagged(started):
    ienv, booking, _ = started
    ienv.ops.post(f"/api/v1/bookings/{booking['id']}/force-release")
    r = submit(ienv.expert, booking)
    assert r.status_code == 200
    b = Booking.objects.get(pk=booking["id"])
    assert b.stage == "submitted" and b.conflict == "RELEASED_DRAFT_ARRIVED"
    assert b.released_draft_expected is False


def test_the_original_expert_still_sees_a_reassigned_job_while_holding_a_draft(started):
    ienv, booking, _ = started
    b_user = ienv.make_user("expert", username="bee")
    Booking.objects.filter(pk=booking["id"]).update(assigned_expert=b_user)
    assert ienv.expert.get(f"/api/v1/bookings/{booking['id']}").status_code == 200  # draft owner
    Inspection.objects.filter(booking_id=booking["id"]).update(status="submitted")
    assert ienv.expert.get(f"/api/v1/bookings/{booking['id']}").status_code == 404  # no draft left


# ---------------------------------------------------------------- ops edits after submit

def test_ops_edit_with_stale_guard_and_access(started):
    ienv, booking, _ = started
    submit(ienv.expert, booking)
    insp = Inspection.objects.get(status="submitted")
    url = f"/api/v1/inspections/{insp.id}"
    r = ienv.ops.patch(url, {"answers": {"inspection": {"odometer": 50}}, "row_version": 0},
                       format="json")
    assert r.status_code == 200 and r.json()["answers"]["inspection"]["odometer"] == 50
    assert r.json()["last_edited_by"] == ienv.ops_user.username and r.json()["row_version"] == 1
    stale = ienv.admin.patch(url, {"answers": {"inspection": {"odometer": 51}}, "row_version": 0},
                             format="json")
    assert stale.status_code == 409 and stale.json()["changed_by"] == ienv.ops_user.username
    sys = ienv.ops.patch(url, {"answers": {"inspection": {"grade": 3}}, "row_version": 1},
                         format="json")
    assert sys.status_code == 403 and sys.json()["keys"] == ["grade"]
    assert ienv.expert.patch(url, {"answers": {}, "row_version": 1}, format="json").status_code == 403


def test_ops_edit_is_validated_and_needs_a_row_version(started):
    ienv, booking, _ = started
    submit(ienv.expert, booking)
    url = f"/api/v1/inspections/{Inspection.objects.get(status='submitted').id}"
    assert ienv.ops.patch(url, {"answers": {}}, format="json").status_code == 400
    r = ienv.ops.patch(url, {"answers": {"inspection": {"odometer": -1}}, "row_version": 0},
                       format="json")
    assert r.status_code == 400 and r.json()["errors"] == {"odometer": "OUT_OF_RANGE"}


def test_listing_a_bookings_inspections_respects_scope(started):
    ienv, booking, _ = started
    submit(ienv.expert, booking)
    url = f"/api/v1/bookings/{booking['id']}/inspections"
    assert len(ienv.ops.get(url).json()) == 1
    assert len(ienv.expert.get(url).json()) == 1       # their own
    other = ienv.make_user("expert", username="e3")
    from rest_framework.test import APIClient

    c = APIClient()
    c.force_authenticate(user=other)
    assert c.get(url).status_code == 404
    assert Role.OPS == "ops"


def test_submit_can_create_the_draft_from_the_phones_pinned_version(ienv, booking):
    """An offline start that never reached the server (e.g. job reassigned meanwhile)."""
    assign(ienv, booking)
    ver = ienv.admin.get(f"/api/v1/forms/{ienv.form_id}").json()["published_version"]["id"]
    r = submit(ienv.expert, booking, form_version=ver)
    assert r.status_code == 200 and r.json()["inspection"]["status"] == "submitted"
    bad = submit(ienv.expert, booking, form_version=99999)
    assert bad.status_code in (400, 409)


# ---------------------------------------------------------------- hidden-field oracle, start errors, ops form

def test_hidden_fields_are_refused_whatever_the_value_so_guesses_leak_nothing(started):
    ienv, booking, _ = started
    submit(ienv.expert, booking)
    insp = Inspection.objects.get(status="submitted")
    # ops sees 'grade' as view (system-filled); make it hidden for ops, then try to confirm a guess
    ienv.admin.patch(f"/api/v1/fields/{_field_id(insp, 'grade')}", {"access": {
        "ops": {s: "hidden" for s in ("submitted", "in_progress", "draft", "assigned",
                                      "completed", "cancelled")}}}, format="json")
    # (published versions are immutable, so exercise the service rule directly)
    from apps.bookings import submissions
    from apps.forms.models import Field

    Field.objects.filter(version=insp.form_version, key="grade").update(
        access={"ops": {"submitted": "hidden"}})
    for guess in (1, 5, None):
        locked = submissions._locked_keys("ops", "submitted", insp.form_version, None,
                                          {"inspection": {"grade": guess}},
                                          {"inspection": {"grade": 5}})
        assert locked == ["grade"]  # same answer for a right and a wrong guess


def _field_id(insp, key):
    from apps.forms.models import Field

    return Field.objects.get(version=insp.form_version, key=key).id


def test_booking_edit_refuses_hidden_fields_even_with_the_stored_value(env, db):
    from apps.forms.models import Form

    form = Form.objects.get(kind="booking")
    d = env.admin.post(f"/api/v1/forms/{form.id}/drafts").json()["id"]
    sec = env.admin.get(f"/api/v1/form-versions/{d}").json()["pages"][0]["sections"][0]["id"]
    env.admin.post(f"/api/v1/sections/{sec}/fields", {"key": "secret_note", "label": "S",
                   "type": "short_text", "access": {"ops": {s: "hidden" for s in (
                       "draft", "assigned", "in_progress", "submitted", "completed",
                       "cancelled")}}}, format="json")
    publish_form(env.admin, form.id)
    b = create(env.admin, secret_note="s3cret").json()
    for value in ("s3cret", "wrong guess"):
        r = env.ops.patch(f"/api/v1/bookings/{b['id']}", {"answers": {"secret_note": value},
                                                          "row_version": 0}, format="json")
        assert r.status_code == 403 and r.json()["keys"] == ["secret_note"]


def test_start_error_paths(ienv, booking):
    from apps.bookings import submissions

    assign(ienv, booking)
    assert start(ienv.expert, booking).status_code == 200
    again = start(ienv.expert, booking)
    assert again.status_code == 409 and again.json()["code"] == "ALREADY_STARTED"
    b = Booking.objects.get(pk=booking["id"])
    other = ienv.make_user("expert", username="e9")
    with pytest.raises(APIException) as e:
        submissions.start(other, b, uuid.uuid4(), None, "pdi", None)
    assert e.value.detail["code"] == "NOT_ASSIGNED"  # type: ignore
    Booking.objects.filter(pk=b.pk).update(stage="cancelled")
    b.refresh_from_db()
    with pytest.raises(APIException) as e:
        submissions.start(ienv.expert_user, b, uuid.uuid4(), None, "pdi", None)
    assert e.value.detail["code"] == "INVALID_STAGE"  # type: ignore


def test_a_bad_uuid_is_a_400(ienv, booking):
    assign(ienv, booking)
    r = ienv.expert.post(f"/api/v1/bookings/{booking['id']}/start", {"client_uuid": "nope"},
                         format="json")
    assert r.status_code == 400


def test_the_experts_form_drops_sections_and_pages_with_nothing_to_show(ienv, booking):
    admin = ienv.admin
    d = admin.post(f"/api/v1/forms/{ienv.form_id}/drafts").json()["id"]
    page = admin.get(f"/api/v1/form-versions/{d}").json()["pages"][0]
    sec = admin.post(f"/api/v1/pages/{page['id']}/sections", {"title": "Ratings"},
                     format="json").json()
    admin.post(f"/api/v1/sections/{sec['id']}/fields", {"key": "rating_two", "label": "R",
               "type": "rating", "config": {"category": "ac"}}, format="json")
    pg2 = admin.post(f"/api/v1/form-versions/{d}/pages", {"title": "Ops only"}, format="json").json()
    s2 = admin.post(f"/api/v1/pages/{pg2['id']}/sections", {"title": "S"}, format="json").json()
    admin.post(f"/api/v1/sections/{s2['id']}/fields", {"key": "rating_three", "label": "R",
               "type": "rating", "config": {"category": "tyres"}}, format="json")
    publish_form(admin, ienv.form_id)
    assign(ienv, booking)
    form = start(ienv.expert, booking).json()["form"]
    assert [s["title"] for p in form["pages"] for s in p["sections"]] == ["Section 1"]
    assert len(form["pages"]) == 1


def test_an_ops_form_is_validated_stored_and_access_controlled(ienv, booking):
    admin = ienv.admin
    ops_form = admin.post("/api/v1/forms", {"key": "ops", "kind": "ops", "name": "Ops"},
                          format="json").json()
    v = ops_form["draft_version"]["id"]
    sec = admin.get(f"/api/v1/form-versions/{v}").json()["pages"][0]["sections"][0]["id"]
    admin.post(f"/api/v1/sections/{sec}/fields", {"key": "pay_mode", "label": "Mode",
               "type": "short_text", "required": True}, format="json")
    admin.post(f"/api/v1/sections/{sec}/fields", {"key": "ops_only", "label": "Ops", "type":
               "short_text", "access": {"expert": {"in_progress": "hidden"}}}, format="json")
    publish_form(admin, ops_form["id"])
    assign(ienv, booking)
    start(ienv.expert, booking)
    bad = submit(ienv.expert, booking, {**GOOD, "ops": {}})
    assert bad.status_code == 400 and bad.json()["errors"] == {"pay_mode": "required"}
    sneaky = submit(ienv.expert, booking, {**GOOD, "ops": {"pay_mode": "upi", "ops_only": "x"}})
    assert sneaky.status_code == 403 and sneaky.json()["keys"] == ["ops_only"]
    ok = submit(ienv.expert, booking, {**GOOD, "ops": {"pay_mode": "upi"}})
    assert ok.status_code == 200
    assert ok.json()["inspection"]["answers"]["ops"] == {"pay_mode": "upi"}


def test_an_ops_edit_that_changes_nothing_keeps_the_row_version(started):
    ienv, booking, _ = started
    submit(ienv.expert, booking)
    insp = Inspection.objects.get(status="submitted")
    r = ienv.ops.patch(f"/api/v1/inspections/{insp.id}",
                       {"answers": {"inspection": {"odometer": 45}}, "row_version": 0},
                       format="json")
    assert r.status_code == 200 and r.json()["row_version"] == 0


def test_experts_read_only_their_own_inspection(started):
    ienv, booking, _ = started
    submit(ienv.expert, booking)
    insp = Inspection.objects.get(status="submitted")
    assert ienv.expert.get(f"/api/v1/inspections/{insp.id}").status_code == 200
    other = ienv.make_user("expert", username="e5")
    from rest_framework.test import APIClient

    c = APIClient()
    c.force_authenticate(user=other)
    assert c.get(f"/api/v1/inspections/{insp.id}").status_code == 404


def test_serializer_without_a_request_returns_everything(started):
    from apps.bookings.serializers import InspectionSerializer

    _, _, body = started
    data = InspectionSerializer(Inspection.objects.get(pk=body["inspection"]["id"])).data
    assert data["status"] == "draft"


def test_a_late_second_submission_on_a_finished_booking_is_stored_without_moving_the_stage(started):
    ienv, booking, _ = started
    Booking.objects.filter(pk=booking["id"]).update(stage="completed")
    r = submit(ienv.expert, booking)
    assert r.status_code == 200
    assert Booking.objects.get(pk=booking["id"]).stage == "completed"
