"""The booking timeline: who did what, and only the field keys each person may see."""
import pytest

from apps.bookings.models import BookingActivity, Inspection
from apps.media.tests.conftest import s3  # noqa: F401

from .conftest import create
from .test_submissions import assign, ienv, started, submit  # noqa: F401  (fixtures)

pytestmark = pytest.mark.django_db


def timeline(client, b):
    r = client.get(f"/api/v1/bookings/{b['id']}/activity")
    assert r.status_code == 200, r.json()
    return r.json()


def test_every_step_lands_on_the_timeline_newest_first(started):
    ienv, booking, _ = started
    submit(ienv.expert, booking)
    insp = Inspection.objects.get(status="submitted")
    ienv.ops.patch(f"/api/v1/inspections/{insp.id}",
                   {"answers": {"inspection": {"odometer": 50, "chassis_no": "MA3YPKCSKTJ273130"}},
                    "row_version": 0}, format="json")
    rows = timeline(ienv.ops, booking)
    kinds = [r["kind"] for r in rows]
    assert kinds[0] == "inspection_edited" and kinds[-1] == "created"
    assert rows[0]["keys"] == ["inspection.chassis_no", "inspection.odometer"]
    assert rows[0]["by"]["role"] == "ops"
    stages = [r["changes"]["stage"][1] for r in rows if "stage" in r["changes"]]
    assert stages[-3:] == ["submitted", "in_progress", "assigned"]
    assigned = next(r for r in rows if "assigned_expert" in r["changes"])
    assert assigned["changes"]["assigned_expert"] == [None, ienv.expert_user.id]


def test_reschedule_keeps_the_old_and_new_time(env):
    from apps.forms.models import MasterListItem

    b = create(env.ops).json()
    reason = MasterListItem.objects.filter(list__key="reschedule_reason").values_list(
        "key", flat=True)[0]
    r = env.ops.post(f"/api/v1/bookings/{b['id']}/reschedule",
                     {"date": "2026-10-20", "time": "11:00", "reason": reason}, format="json")
    assert r.status_code == 200, r.json()
    top = timeline(env.ops, b)[0]
    assert top["changes"] == {"inspection_date": ["2026-10-14", "2026-10-20"],
                              "inspection_time": ["15:30", "11:00"]}


def test_an_ops_edit_keeps_the_old_and_new_value(env):
    b = create(env.ops).json()
    env.ops.patch(f"/api/v1/bookings/{b['id']}", {"answers": {"customer_name": "Asha Rao"},
                                                   "row_version": 0}, format="json")
    top = timeline(env.ops, b)[0]
    assert top["kind"] == "edited" and top["keys"] == ["customer_name"]
    assert top["changes"]["customer_name"][1] == "Asha Rao"
    assert top["changes"]["customer_name"][0] == b["answers"]["customer_name"]


def test_an_inspection_edit_keeps_each_answers_old_and_new_value(started):
    ienv, booking, _ = started
    submit(ienv.expert, booking)
    insp = Inspection.objects.get(status="submitted")
    before = insp.answers["inspection"].get("odometer")
    ienv.ops.patch(f"/api/v1/inspections/{insp.id}",
                   {"answers": {"inspection": {"odometer": 50}}, "row_version": 0}, format="json")
    top = timeline(ienv.ops, booking)[0]
    assert top["changes"] == {"inspection.odometer": [before, 50]}


def test_long_text_is_cut_and_files_are_counted():
    from apps.bookings.activity import MAX_TEXT, _kept

    file_a, file_b = "8f14e45f-ceea-467a-9b3c-2c1d2e3f4a5b", "c9f0f895-fb98-4b91-8f2e-3a4b5c6d7e8f"
    assert _kept("note", ["x" * 300, "short"]) == ["x" * MAX_TEXT + "…", "short"]
    assert _kept("photos", [[file_a], [file_a, file_b]]) == ["1 file", "2 files"]
    assert _kept("signature", [None, file_a]) == [None, "1 file"]
    assert _kept("colours", [["red"], ["red", "blue"]]) == [["red"], ["red", "blue"]]
    assert _kept("media", [file_a, file_b]) == [file_a, file_b]          # kept: Admin opens it
    assert _kept("ref", [None, "x" * 36]) == [None, "x" * 36]            # 36 long, not a file
    assert _kept("odd", "plain") == "plain"                              # not an [old, new] pair
    big = {"k": "y" * 300}
    assert _kept("where", [None, big])[1].endswith("…")


def test_a_deleted_bookings_history_keeps_no_customer_values(env):
    b = create(env.ops).json()
    env.ops.patch(f"/api/v1/bookings/{b['id']}", {"answers": {"customer_name": "Asha Rao"},
                                                   "row_version": 0}, format="json")
    r = env.admin.delete(f"/api/v1/bookings/{b['id']}")
    assert r.status_code == 204, r.content
    rows = BookingActivity.objects.filter(booking_ref=b["booking_id"])
    edited = rows.get(kind="edited")
    assert edited.keys == ["customer_name"] and edited.changes == {}
    assert any("stage" in r.changes for r in rows) or rows.filter(kind="created").exists()


def test_keys_hidden_from_a_role_are_left_out(env):
    from apps.forms.models import Form

    from .test_submissions import publish_form

    form = Form.objects.get(type="booking")
    d = env.admin.post(f"/api/v1/forms/{form.id}/drafts").json()["id"]
    sec = env.admin.get(f"/api/v1/form-versions/{d}").json()["pages"][0]["sections"][0]["id"]
    env.admin.post(f"/api/v1/sections/{sec}/fields", {"key": "secret_note", "label": "S",
                   "type": "short_text", "access": {"ops": {s: "hidden" for s in (
                       "draft", "assigned", "in_progress", "submitted", "completed",
                       "cancelled")}}}, format="json")
    publish_form(env.admin, form.id)
    b = create(env.admin).json()
    env.admin.patch(f"/api/v1/bookings/{b['id']}",
                    {"answers": {"secret_note": "x", "customer_name": "B"}, "row_version": 0},
                    format="json")
    assert timeline(env.admin, b)[0]["keys"] == ["customer_name", "secret_note"]
    assert timeline(env.admin, b)[0]["changes"]["secret_note"] == [None, "x"]
    ops_row = timeline(env.ops, b)[0]
    assert ops_row["keys"] == ["customer_name"] and set(ops_row["changes"]) == {"customer_name"}


def test_only_people_who_see_the_booking_see_its_timeline(env, make_user, api_as):
    from apps.accounts.models import Role

    b = create(env.ops).json()
    other, _ = api_as(Role.EXPERT)
    assert other.get(f"/api/v1/bookings/{b['id']}/activity").status_code in (403, 404)


def test_the_list_can_be_ordered_by_schedule(env):
    for bid, d, t in (("B1", "2026-10-15", "09:00"), ("B2", "2026-10-14", "17:00"),
                      ("B3", "2026-10-14", "08:30")):
        r = create(env.ops, booking_id=bid, inspection_date=d, inspection_time=t)
        assert r.status_code == 201
    rows = env.ops.get("/api/v1/bookings?order=schedule").json()["results"]
    ids = [b["booking_id"] for b in rows]
    assert ids == ["B3", "B2", "B1"]
    assert env.ops.get("/api/v1/bookings?order=nope").status_code == 400


def test_schedule_values_of_a_hidden_field_are_not_shown(env):
    from apps.forms.models import Form

    from .test_submissions import publish_form

    form = Form.objects.get(type="booking")
    d = env.admin.post(f"/api/v1/forms/{form.id}/drafts").json()["id"]
    tree = env.admin.get(f"/api/v1/form-versions/{d}").json()
    field = next(f for p in tree["pages"] for s in p["sections"] for f in s["fields"]
                 if f["key"] == "inspection_time")
    hidden = {s: "hidden" for s in ("draft", "assigned", "in_progress", "submitted",
                                    "completed", "cancelled")}
    r = env.admin.patch(f"/api/v1/fields/{field['id']}", {"access": {"ops": hidden}},
                        format="json")
    assert r.status_code == 200, r.json()
    publish_form(env.admin, form.id)
    from apps.bookings import activity
    from apps.bookings.models import Booking

    b = create(env.admin).json()
    booking = Booking.objects.get(pk=b["id"])
    activity.log(booking, env.admin_user, "changed",
                 {"inspection_time": ["15:30", "11:00"], "stage": ["draft", "draft"]})
    top = timeline(env.ops, b)[0]
    assert top["changes"] == {"stage": ["draft", "draft"]} and top["keys"] == ["stage"]
    assert "inspection_time" in timeline(env.admin, b)[0]["changes"]


def test_rows_about_a_form_whose_submissions_are_hidden_are_left_out(started):
    from apps.forms.models import Form

    ienv, booking, _ = started
    submit(ienv.expert, booking)
    insp = Inspection.objects.get(status="submitted")
    ienv.ops.patch(f"/api/v1/inspections/{insp.id}",
                   {"answers": {"inspection": {"odometer": 51}}, "row_version": 0}, format="json")
    assert timeline(ienv.ops, booking)[0]["kind"] == "inspection_edited"
    Form.objects.filter(pk=insp.form_version.form_id).update(submission_roles=["admin"])
    kinds = [r["kind"] for r in timeline(ienv.ops, booking)]
    assert "inspection_edited" not in kinds and "created" in kinds
