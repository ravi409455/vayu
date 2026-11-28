"""checkin.completed through integrations: set up once on the Check-in form, one integration
covers every inspection type, and each event says which type and form it came from."""
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.bookings.models import Booking, Inspection
from apps.bookings.tests.conftest import create
from apps.bookings.tests.test_checkin_event import check_in, register, upload
from apps.bookings.tests.test_submissions import _publish_with, assign, start
from apps.forms.models import Form
from apps.integrations import values, webhooks
from apps.media.tests.conftest import s3  # noqa: F401  (autouse: in-memory S3)

from .conftest import HOOK, make

pytestmark = pytest.mark.django_db
EVENT = "checkin.completed"


@pytest.fixture
def cenv(ienv):
    _publish_with(ienv.admin, "start")
    ienv.start_form = Form.objects.get(type="start").id
    return ienv


def sent(http):
    import json

    return [json.loads(c.request.body) for c in http.calls if c.request.url == HOOK]


def done_check_in(env, b, settings, **extra):
    assign(env, b)
    init, data = register(env, b)
    upload(env, init, data, settings)
    return check_in(env, b, init["id"], **extra), init["id"]


def test_one_check_in_form_integration_gets_every_type_with_its_own_type(cenv, http, settings):
    from apps.bookings.tests.conftest import custom_form, publish_draft

    publish_draft(cenv.admin, custom_form(cenv.admin, "used_car", "Used car")["id"])
    make(cenv, cenv.start_form, event=EVENT)
    make(cenv, cenv.form_id, name="PDI form", event="inspection.started")
    pdi = create(cenv.ops).json()
    used = create(cenv.ops, booking_id="UC1", inspection_type="used_car").json()
    http.calls.reset()
    done_check_in(cenv, pdi, settings)
    assign(cenv, used)
    init, data = register(cenv, used)
    upload(cenv, init, data, settings)
    r = start(cenv.expert, used, start_answers={"selfie": [init["id"]]}, inspection_type="used_car")
    assert r.status_code == 200, r.json()
    bodies = [b for b in sent(http) if b["event"] == EVENT]
    assert [b["job"]["type"] for b in bodies] == ["pdi", "used_car"]
    assert bodies[0]["job"]["form"].startswith("PDI v")
    assert [b["event"] for b in sent(http) if b["event"] != EVENT] == ["inspection.started"]


def test_the_event_and_form_pairs_come_from_one_table(cenv):
    start_form = cenv.start_form
    assert make(cenv, start_form, event=EVENT)["event"] == EVENT
    for form, event in ((start_form, "inspection.started"), (cenv.form_id, EVENT),
                        (Form.objects.get(type="booking").id, EVENT)):
        r = cenv.admin.post("/api/v1/integrations", {"form": form, "name": "x", "url": HOOK,
                                                     "event": event}, format="json")
        assert r.status_code == 400 and r.json()["code"] == "INVALID_EVENT", (form, event)
    end = Form.objects.get(type="end").id
    r = cenv.admin.post("/api/v1/integrations", {"form": end, "name": "x", "url": HOOK,
                                                 "event": EVENT}, format="json")
    assert r.json()["code"] == "INVALID_FORM"
    lists = {f: cenv.admin.get(f"/api/v1/integrations/events?form={f}").json()
             for f in (start_form, cenv.form_id)}
    assert lists[start_form] == [EVENT]
    assert EVENT not in lists[cenv.form_id] and "inspection.started" in lists[cenv.form_id]
    assert EVENT in cenv.admin.get("/api/v1/integrations/events").json()     # every event


def test_the_picker_for_the_check_in_form(cenv):
    refs = {e["ref"]: e for e in cenv.admin.get(
        f"/api/v1/integrations/catalogue?form={cenv.start_form}&event={EVENT}").json()}
    assert {"start.selfie", "start.checkin_gps"} - set(refs) == {"start.selfie"}    # a photo: links
    assert "link.photos.selfie" in refs and "booking.customer_name" in refs
    for ref in ("checkin.number", "checkin.expert", "checkin.expert_phone", "checkin.time",
                "checkin.received_at", "checkin.late_minutes", "checkin.unverified_time",
                "checkin.missing_files", "job.type", "job.form", "event.name"):
        assert ref in refs, ref
    assert refs["checkin.number"]["group"] == "checkin"
    assert not [r for r in refs if r.split(".")[0] in ("inspection", "end", "result")]
    assert not [r for r in refs if r in ("link.pdf", "link.image_zip", "link.video_zip")]


def test_the_values_of_a_check_in(cenv, booking, settings):
    cenv.expert_user.phone = "9000000001"
    cenv.expert_user.save()
    insp, sid = done_check_in(cenv, booking, settings)
    d = SimpleNamespace(booking_uuid=booking["id"], event=EVENT, id="d", created_at=timezone.now(),
                        context={"inspection": str(insp.id), "missing": ["Selfie"], "number": 1})
    r = values.Resolver(d)
    assert r.get("checkin.number") == 1
    assert r.get("checkin.expert") == cenv.expert_user.shown_name
    assert r.get("checkin.expert_phone") == "9000000001"
    assert r.get("checkin.time") == insp.client_started_at.isoformat()
    assert r.get("checkin.received_at") == insp.created_at.isoformat()
    # booked 2026-10-14 15:30 local, the phone pressed Start at 10:00 the same day: early
    assert r.get("checkin.late_minutes") == -330
    assert r.get("checkin.unverified_time") is False
    assert r.get("checkin.missing_files") == ["Selfie"]
    [link] = r.get("link.photos.selfie")
    assert sid in link
    assert r.get("job.form").startswith("PDI v")


def test_late_minutes_use_the_server_time_when_the_phone_clock_is_not_trusted(cenv, booking,
                                                                               settings):
    insp, _ = done_check_in(cenv, booking, settings, unverified_time=True)
    d = SimpleNamespace(booking_uuid=booking["id"], event=EVENT, id="d",
                        created_at=timezone.now(), context={"inspection": str(insp.id)})
    from apps.bookings import timing

    b = Booking.objects.get(pk=booking["id"])
    expect = round((insp.created_at - timing.slot(b)).total_seconds() / 60)
    assert values.Resolver(d).get("checkin.late_minutes") == expect
    Inspection.objects.filter(pk=insp.pk).update(unverified_time=False, client_started_at=None)
    assert values.Resolver(d).get("checkin.late_minutes") == expect          # older app: none
    Booking.objects.filter(pk=booking["id"]).update(inspection_date=None)
    assert values.Resolver(d).get("checkin.late_minutes") is None           # no slot booked


def test_a_second_check_in_sends_its_own_expert_and_photos(cenv, booking, settings):
    first, first_sid = done_check_in(cenv, booking, settings)
    assert cenv.ops.post(f"/api/v1/bookings/{booking['id']}/force-release").status_code == 200
    from rest_framework.test import APIClient

    other, client = cenv.make_user(), APIClient()
    client.force_authenticate(other)
    env2 = SimpleNamespace(expert=client, ops=cenv.ops)
    assign(cenv, booking, other)
    init, data = register(env2, booking)
    upload(env2, init, data, settings)
    second = check_in(env2, booking, init["id"])
    d = SimpleNamespace(booking_uuid=booking["id"], event=EVENT, id="d",
                        created_at=timezone.now(),
                        context={"inspection": str(second.id), "number": 2})
    r = values.Resolver(d)
    assert r.get("checkin.expert") == other.shown_name and r.get("checkin.number") == 2
    [link] = r.get("link.photos.selfie")
    assert init["id"] in link and first_sid not in link


def test_the_standard_body(cenv, http, booking, settings):
    make(cenv, cenv.start_form, event=EVENT, fields=["customer_name", "checkin_gps"])
    insp, sid = done_check_in(cenv, booking, settings)
    [body] = [b for b in sent(http) if b["event"] == EVENT]
    assert body["inspection"] == str(insp.id)
    assert body["data"]["booking"] == {"customer_name": "Asha"}
    assert set(body["data"]["start"]) <= {"checkin_gps"}
    c = body["checkin"]
    assert c["number"] == 1 and c["missing_files"] == [] and c["unverified_time"] is False
    assert c["time"] and c["received_at"] and "late_minutes" in c and c["expert"]
    assert sid in c["photos"]["selfie"][0]
    assert body["job"]["type"] == "pdi" and "pdf_url" not in body


def test_the_sample_body_has_the_same_shape(cenv):
    i = make(cenv, cenv.start_form, event=EVENT)
    r = cenv.admin.post("/api/v1/integrations/preview", {
        "form": cenv.start_form, "event": EVENT, "url": HOOK}, format="json")
    assert r.status_code == 200, r.json()
    import json

    body = json.loads(r.json()["body"])
    assert r.json()["sample"] is True                    # no booking has checked in yet
    assert set(body) >= {"data", "checkin", "job"} and "selfie" in body["checkin"]["photos"]
    assert i["id"]


def test_preview_picks_a_booking_that_has_checked_in(cenv, booking, settings):
    create(cenv.ops, booking_id="NEWER")                   # newer, but no check-in
    done_check_in(cenv, booking, settings)
    r = cenv.admin.post("/api/v1/integrations/preview", {
        "form": cenv.start_form, "event": EVENT, "url": HOOK}, format="json")
    assert r.json()["booking"] == booking["id"] and r.json()["sample"] is False


def test_the_routing_table_covers_every_event():
    every = {e for events in webhooks.EVENTS_FOR.values() for e in events}
    assert every == set(webhooks.EVENTS)


def test_the_test_button_sends_the_check_in_body(cenv, http, booking, settings):
    i = make(cenv, cenv.start_form, event=EVENT)
    done_check_in(cenv, booking, settings)
    http.calls.reset()
    r = cenv.admin.post(f"/api/v1/integrations/{i['id']}/test", {}, format="json")
    assert r.json()["status"] == "success"
    [body] = sent(http)
    assert body["event"] == "test.ping" and body["checkin"]["expert"] and "selfie" in body["checkin"]["photos"]


def test_the_field_list_of_a_check_in_integration_takes_check_in_fields(cenv):
    i = make(cenv, cenv.start_form, event=EVENT, fields=["customer_name", "checkin_gps", "nope"])
    assert i["broken_refs"] == ["field.nope"]


def test_a_booking_without_a_check_in_has_no_check_in_values(cenv, booking):
    d = SimpleNamespace(booking_uuid=booking["id"], event=EVENT, id="d", created_at=timezone.now(),
                        context={})
    r = values.Resolver(d)
    assert r.get("checkin.expert") is None and r.get("checkin.late_minutes") is None
    assert r.get("checkin.missing_files") == [] and r.photo_refs("start") == []


def test_the_body_without_data(cenv, http, booking, settings):
    make(cenv, cenv.start_form, event=EVENT, include_data=False)
    done_check_in(cenv, booking, settings)
    [body] = [b for b in sent(http) if b["event"] == EVENT]
    assert "data" not in body and body["checkin"]["number"] == 1
