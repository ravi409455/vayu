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


def test_values_of_ordinary_fields_are_never_stored(env):
    b = create(env.ops).json()
    env.ops.patch(f"/api/v1/bookings/{b['id']}", {"answers": {"customer_name": "Asha Rao"},
                                                   "row_version": 0}, format="json")
    row = BookingActivity.objects.filter(booking_id=b["id"], kind="edited").get()
    assert row.keys == ["customer_name"] and row.changes == {}


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
    assert timeline(env.ops, b)[0]["keys"] == ["customer_name"]


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
