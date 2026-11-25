import json
import uuid
from datetime import timedelta

import pytest
import requests
import responses
from django.utils import timezone

from apps.bookings.tests.conftest import create
from apps.bookings.tests.test_submissions import GOOD, assign, start, submit
from apps.core import events
from apps.integrations import tasks, webhooks
from apps.integrations.models import Delivery, Integration
from apps.reports.tests.test_reports import renv  # noqa: F401

from .conftest import HOOK, booking_form_id, make

pytestmark = pytest.mark.django_db


def sent(http):
    return [c for c in http.calls if c.request.url == HOOK]


def body_of(call):
    return json.loads(call.request.body)


# ---------------------------------------------------------------- CRUD, validation, audit

def test_crud_is_admin_only_and_audited(ienv):
    from apps.accounts.models import AuditLog

    for client in (ienv.ops, ienv.expert):
        assert client.get("/api/v1/integrations").status_code == 403
        assert client.post("/api/v1/integrations", {}, format="json").status_code == 403
    i = make(ienv, ienv.form_id, event="booking.created")
    assert "secret" not in i and "template" not in i and i["method"] == "POST"
    again = ienv.admin.get(f"/api/v1/integrations/{i['id']}").json()
    assert again["event"] == "booking.created" and again["broken_refs"] == []
    r = ienv.admin.patch(f"/api/v1/integrations/{i['id']}", {"name": "ERP 2", "is_active": False,
                         "event": "pdf.ready"}, format="json")
    assert r.json()["name"] == "ERP 2" and r.json()["is_active"] is False
    assert ienv.admin.get(f"/api/v1/integrations?form={ienv.form_id}").json()[0]["id"] == i["id"]
    assert ienv.admin.delete(f"/api/v1/integrations/{i['id']}").status_code == 204
    actions = set(AuditLog.objects.values_list("action", flat=True))
    assert {"integration.create", "integration.update", "integration.delete"} <= actions


def test_several_integrations_per_form(ienv):
    make(ienv, ienv.form_id, name="A")
    make(ienv, ienv.form_id, name="B", url="https://other.example.com/x")
    assert len(ienv.admin.get("/api/v1/integrations").json()) == 2


@pytest.mark.parametrize("change,code", [
    ({"form": 999999}, "INVALID_FORM"), ({"form": "x"}, "INVALID_FORM"),
    ({"name": ""}, "INVALID_NAME"), ({"name": 5}, "INVALID_NAME"),
    ({"url": "ftp://x.example.com"}, "INVALID_URL"), ({"url": 5}, "INVALID_URL"),
    ({"url": "https://user:pw@hooks.example.com/"}, "INVALID_URL"),
    ({"event": ""}, "INVALID_EVENT"), ({"event": "nope"}, "INVALID_EVENT"),
    ({"event": ["booking.created"]}, "INVALID_EVENT"), ({"method": "TRACE"}, "INVALID_METHOD"),
    ({"url": "https://hooks.example.com/{{job.booking_id}}/x?a={{job.city}}"}, "INVALID_URL"),
    ({"url": "https://{{job.city}}.example.com/x"}, "INVALID_URL"),
    ({"url": "https://hooks.example.com/{{booking.nope}}"}, "UNKNOWN_VALUE"),
    ({"url": "https://hooks.example.com/{{ unclosed"}, "INVALID_VALUE"),
    ({"query": "a"}, "INVALID_QUERY"), ({"query": [{"key": "", "value": "x"}]}, "INVALID_QUERY"),
    ({"query": [{"key": "a", "value": "{{nope.x}}"}]}, "UNKNOWN_VALUE"),
    ({"headers": [{"key": "Content-Type", "value": "x"}]}, "LOCKED_HEADER"),
    ({"headers": [{"key": "x-vayu-event", "value": "x"}]}, "LOCKED_HEADER"),
    ({"headers": [{"key": "Host", "value": "x"}]}, "LOCKED_HEADER"),
    ({"headers": [{"key": "bad name", "value": "x"}]}, "INVALID_HEADERS"),
    ({"headers": [{"key": "A", "value": "x"}, {"key": "a", "value": "y"}]}, "INVALID_HEADERS"),
    ({"headers": [{"key": "A", "value": "two\nlines"}]}, "INVALID_VALUE"),
    ({"body_mode": "weird"}, "INVALID_BODY"),
    ({"body_mode": "custom", "body": "text"}, "INVALID_BODY"),
    ({"body_mode": "custom", "body": 5}, "INVALID_BODY"),
    ({"body_mode": "custom", "body": {"": 1}}, "INVALID_BODY"),
    ({"body_mode": "custom", "body": {"{{job.id}}": 1}}, "INVALID_BODY"),
    ({"body_mode": "custom", "body": {"a": ["x", {"b": "{{inspection.zzz}}"}]}},
     "UNKNOWN_VALUE"),
    ({"body_mode": "custom", "body": {"a": "{{ unclosed"}}, "INVALID_VALUE"),
    ({"include_data": "yes"}, "INVALID_TOGGLE"), ({"fields": "a"}, "INVALID_FIELDS"),
    ({"fields": [1]}, "INVALID_FIELDS"),
])
def test_bad_integrations_are_refused(ienv, change, code):
    base = {"form": ienv.form_id, "name": "ERP", "url": HOOK, "event": "booking.created"}
    r = ienv.admin.post("/api/v1/integrations", {**base, **change}, format="json")
    assert r.status_code == 400 and r.json()["code"] == code


@pytest.mark.parametrize("ftype", ["start", "end"])
def test_start_and_end_forms_cannot_have_integrations(ienv, ftype):
    from apps.forms.models import Form

    system_form = Form.objects.get(type=ftype)
    r = ienv.admin.post("/api/v1/integrations", {"form": system_form.id, "name": "x", "url": HOOK,
                                                 "event": "booking.created"}, format="json")
    assert r.json()["code"] == "INVALID_FORM"


def test_plain_http_and_private_addresses_are_refused_in_production_mode(ienv, settings,
                                                                          monkeypatch):
    settings.WEBHOOK_ALLOW_HTTP = False
    base = {"form": ienv.form_id, "name": "x", "event": "booking.created"}
    r = ienv.admin.post("/api/v1/integrations", {**base, "url": "http://hooks.example.com/"},
                        format="json")
    assert r.json()["reason"] == "https_required"
    monkeypatch.setattr(webhooks, "resolve", lambda host: ["10.0.0.5"])
    r = ienv.admin.post("/api/v1/integrations", {**base, "url": HOOK}, format="json")
    assert r.json()["reason"] == "blocked_address"
    monkeypatch.setattr(webhooks, "resolve", lambda host: ["93.184.216.34", "127.0.0.1"])
    assert ienv.admin.post("/api/v1/integrations", {**base, "url": HOOK},
                           format="json").json()["reason"] == "blocked_address"

    def nxdomain(host):
        raise OSError("nope")

    monkeypatch.setattr(webhooks, "resolve", nxdomain)
    assert ienv.admin.post("/api/v1/integrations", {**base, "url": HOOK},
                           format="json").json()["reason"] == "host_not_found"


def test_the_event_catalog_lists_the_nine_events(ienv):
    got = ienv.admin.get("/api/v1/integrations/events").json()
    assert len(got) == 9 and "alert.stuck_upload" in got and "pdf.ready" in got


# ---------------------------------------------------------------- which events go where

def test_only_subscribed_events_are_sent(ienv, http):
    make(ienv, booking_form_id(), event="booking.deleted")
    b = create(ienv.ops).json()
    assign(ienv, b)
    assert sent(http) == []                                  # created/updated not subscribed
    ienv.admin.delete(f"/api/v1/bookings/{b['id']}")
    assert [body_of(c)["event"] for c in sent(http)] == ["booking.deleted"]


def test_booking_form_integrations_get_only_booking_events(ienv, http, booking):
    for event in ("booking.created", "booking.updated", "booking.deleted"):
        make(ienv, booking_form_id(), name=event, event=event)
    http.calls.reset()
    assign(ienv, booking)
    start(ienv.expert, booking)
    submit(ienv.expert, booking)
    got = {body_of(c)["event"] for c in sent(http)}
    assert got == {"booking.updated"}                        # not inspection/media/pdf events
    for event in ("inspection.submitted", "pdf.ready", "alert.conflict"):
        r = ienv.admin.post("/api/v1/integrations", {"form": booking_form_id(), "name": "x",
                            "url": HOOK, "event": event}, format="json")
        assert r.json()["code"] == "INVALID_EVENT"           # a booking form has booking events only


def test_inspection_form_integrations_get_every_event_for_their_type(ienv, http, booking):
    for event in webhooks.EVENTS:
        make(ienv, ienv.form_id, name=event, event=event)
    assign(ienv, booking)
    start(ienv.expert, booking)
    submit(ienv.expert, booking)
    got = [body_of(c)["event"] for c in sent(http)]
    assert {"booking.updated", "inspection.started", "inspection.submitted",
            "media.completed"} <= set(got)


def test_other_types_inactive_and_deleted_forms_do_not_fire(ienv, http, booking):
    i = make(ienv, ienv.form_id, event="booking.updated")
    from apps.bookings.models import Booking

    Booking.objects.filter(pk=booking["id"]).update(inspection_type="used_car")
    events.emit("booking.updated", booking=booking["id"], booking_id="SA37926")
    assert sent(http) == []                                  # a different inspection type
    Booking.objects.filter(pk=booking["id"]).update(inspection_type="pdi")
    ienv.admin.patch(f"/api/v1/integrations/{i['id']}", {"is_active": False}, format="json")
    events.emit("booking.updated", booking=booking["id"], booking_id="SA37926")
    assert sent(http) == []
    ienv.admin.patch(f"/api/v1/integrations/{i['id']}", {"is_active": True}, format="json")
    events.emit("booking.updated", booking=booking["id"], booking_id="SA37926")
    assert len(sent(http)) == 1


def test_unknown_internal_events_are_ignored(ienv, http, booking):
    make(ienv, booking_form_id(), event="booking.updated")
    http.calls.reset()
    events.emit("inspection.updated", booking=booking["id"], booking_id="x")
    events.emit("booking.created")                           # no booking in the payload
    assert sent(http) == []


def test_one_assignment_is_one_booking_updated_delivery(ienv, http, booking):
    """F-207: booking.assigned is for the bell only; its booking.updated already went."""
    make(ienv, ienv.form_id, event="booking.updated")
    from apps.bookings.tests.test_submissions import assign as assign_expert

    assign_expert(ienv, booking)
    assert [body_of(c)["event"] for c in sent(http)] == ["booking.updated"]


@pytest.mark.parametrize("internal,public", [
    ("alert.late_work", "alert.conflict"), ("alert.type_change_rejected", "alert.conflict"),
    ("alert.conflict", "alert.conflict"), ("alert.stuck_upload", "alert.stuck_upload"),
    ("pdf.ready", "pdf.ready"), ("media.completed", "media.completed")])
def test_internal_events_map_to_the_public_ones(ienv, http, booking, internal, public):
    make(ienv, ienv.form_id, event=public)
    events.emit(internal, booking=booking["id"], booking_id="SA37926")
    assert [body_of(c)["event"] for c in sent(http)] == [public]


def test_a_real_conflict_fires_alert_conflict(ienv, http, booking):
    make(ienv, ienv.form_id, event="alert.conflict")
    assign(ienv, booking)
    start(ienv.expert, booking)
    from apps.bookings.models import Booking, Inspection
    other = ienv.make_user("expert")
    Booking.objects.filter(pk=booking["id"]).update(assigned_expert=other)   # reassigned offline
    mine = Inspection.objects.get(booking_id=booking["id"])
    Inspection.objects.create(booking_id=booking["id"], expert=other,      # and the other began
                              form_version=mine.form_version, client_start_uuid=uuid.uuid4())
    submit(ienv.expert, booking)
    bodies = [body_of(c) for c in sent(http)]
    assert bodies and bodies[0]["event"] == "alert.conflict"
    assert bodies[0]["alert"] == "CONFLICT_TWO_EXPERTS"


def test_a_booking_id_edit_carries_old_and_new(ienv, http, booking):
    make(ienv, booking_form_id(), event="booking.updated", include_data=False)
    b = ienv.ops.get(f"/api/v1/bookings/{booking['id']}").json()
    ienv.ops.patch(f"/api/v1/bookings/{booking['id']}", {
        "row_version": b["row_version"], "answers": {"booking_id": "SA99999",
                                                       "customer_name": "Someone Else"}},
        format="json")
    p = body_of(sent(http)[-1])
    assert p["booking_id_change"] == {"from": "SA37926", "to": "SA99999"}
    assert p["booking"]["booking_id"] == "SA99999" and p["booking"]["id"] == booking["id"]
    assert sorted(p["changed_keys"]) == ["booking_id", "customer_name"]
    assert "Someone Else" not in json.dumps(p)               # no data without 'full data'


# ---------------------------------------------------------------- the body

def test_default_payload_has_both_ids_and_the_event(ienv, http, booking):
    make(ienv, booking_form_id(), include_data=False)
    create(ienv.ops, booking_id="ZZ1")
    p = body_of(sent(http)[-1])
    assert p["event"] == "booking.created" and p["booking"]["booking_id"] == "ZZ1"
    assert p["booking"]["id"] and p["delivery"] and p["occurred_at"] and "data" not in p
    r = sent(http)[-1].request
    assert r.headers["X-Vayu-Event"] == "booking.created"
    assert r.headers["X-Vayu-Delivery"] == p["delivery"]
    assert r.headers["Content-Type"] == "application/json"


def test_full_data_is_scoped_to_the_integrations_fields(ienv, http):
    make(ienv, booking_form_id(), fields=["city", "booking_id"])
    create(ienv.ops, booking_id="ZZ2")
    data = body_of(sent(http)[-1])["data"]
    assert data["booking"] == {"booking_id": "ZZ2", "city": "delhi"}
    assert "customer_phone" not in json.dumps(data)
    assert "start" not in data and "end" not in data       # scoped hooks never get them


def test_full_data_includes_the_inspection_after_submission(ienv, http, booking):
    make(ienv, ienv.form_id, event="inspection.submitted")
    assign(ienv, booking)
    start(ienv.expert, booking)
    submit(ienv.expert, booking)
    data = body_of(sent(http)[-1])["data"]
    assert data["inspection"]["chassis_no"] == GOOD["inspection"]["chassis_no"]
    assert data["booking"]["customer_name"] == "Asha"
    assert data["start"] == {} and data["end"] == {}      # everything unscoped: start / end too


@pytest.mark.parametrize("pdf,image,video", [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 1)])
def test_link_toggles(renv, http, settings, pdf, image, video):
    from apps.reports.tests.test_reports import complete_job, set_template

    make(renv, renv.form_id, event="pdf.ready", include_pdf=bool(pdf),
         include_image_zip=bool(image), include_video_zip=bool(video))
    set_template(renv)
    complete_job(renv, settings=settings)
    p = body_of(sent(http)[-1])
    assert p["event"] == "pdf.ready"
    assert ("pdf_url" in p) == bool(pdf) and ("image_zip_url" in p) == bool(image)
    assert ("video_zip_url" in p) == bool(video)
    if pdf:
        assert p["pdf_url"].startswith("https://") and "X-Amz-Expires=604800" in p["pdf_url"]
    if image:
        assert "/zip/" in p["image_zip_url"]
    if video:
        assert p["video_zip_url"] is None                    # no video was uploaded


def test_toggles_are_null_when_nothing_exists_yet(ienv, http):
    make(ienv, booking_form_id(), include_pdf=True, include_image_zip=True)
    create(ienv.ops, booking_id="ZZ3")
    p = body_of(sent(http)[-1])
    assert p["pdf_url"] is None and p["image_zip_url"] is None


# ---------------------------------------------------------------- retries

def delivery(ienv, ref="R1", **kw):
    make(ienv, booking_form_id(), **kw)
    create(ienv.ops, booking_id=ref)
    return Delivery.objects.get(booking_ref=ref)


def test_success_is_final(ienv, http, logged):
    d = delivery(ienv)
    assert d.status == "success" and d.attempts == 1 and d.response_status == 200
    row = logged("webhook.delivery")[-1]
    assert (row["delivery"], row["status"], row["http"], row["attempt"]) == (str(d.id), "success",
                                                                             200, 1)
    assert row["duration_ms"] >= 0 and "url" not in row
    assert d.error == "" and d.next_retry_at is None


@pytest.mark.parametrize("status", [500, 502, 503, 429])
def test_5xx_and_429_are_retried(ienv, status, logged):
    with responses.RequestsMock() as r:
        r.add(responses.POST, HOOK, status=status)
        d = delivery(ienv)
    assert d.status == "retrying" and d.error == f"http_{status}" and d.response_status == status
    assert abs((d.next_retry_at - timezone.now()).total_seconds() - 60) < 5
    assert logged("webhook.delivery")[-1]["status"] == "retrying"


@pytest.mark.parametrize("exc,reason", [(requests.Timeout(), "timeout"),
                                        (requests.ConnectionError(), "connection_error")])
def test_timeouts_and_network_errors_are_retried(ienv, exc, reason):
    with responses.RequestsMock() as r:
        r.add(responses.POST, HOOK, body=exc)
        d = delivery(ienv)
    assert d.status == "retrying" and d.error == reason and d.response_status is None


@pytest.mark.parametrize("status", [400, 401, 403, 404, 410, 422, 301, 302])
def test_other_answers_are_final_and_not_retried(ienv, status):
    with responses.RequestsMock() as r:
        r.add(responses.POST, HOOK, status=status, headers={"Location": "https://evil.example/"})
        d = delivery(ienv)
        assert len(r.calls) == 1                              # redirects are never followed
    assert d.status == "failed" and d.error == f"http_{status}" and d.next_retry_at is None


def test_the_backoff_is_1m_5m_30m_2h_6h_12h_then_gives_up(ienv):
    seen = []
    with responses.RequestsMock() as r:
        r.add(responses.POST, HOOK, status=503)
        d = delivery(ienv)
        for _ in range(6):
            seen.append(round((d.next_retry_at - d.last_attempt_at).total_seconds()))
            Delivery.objects.filter(pk=d.pk).update(next_retry_at=timezone.now()
                                                    - timedelta(seconds=1))
            assert tasks.retry_due() == 1
            d.refresh_from_db()
    assert seen == [60, 300, 1800, 7200, 21600, 43200]
    assert d.status == "failed" and d.error == "retries_exhausted" and d.attempts == 7


def test_a_later_success_ends_the_retries(ienv):
    with responses.RequestsMock() as r:
        r.add(responses.POST, HOOK, status=500)
        r.add(responses.POST, HOOK, status=200)
        d = delivery(ienv)
        Delivery.objects.filter(pk=d.pk).update(next_retry_at=timezone.now() - timedelta(seconds=1))
        tasks.retry_due()
    d.refresh_from_db()
    assert d.status == "success" and d.attempts == 2 and d.error == ""


def test_retry_due_only_takes_what_is_due(ienv):
    with responses.RequestsMock() as r:
        r.add(responses.POST, HOOK, status=500)
        d = delivery(ienv)
        assert tasks.retry_due() == 0                         # not due yet
        assert len(r.calls) == 1
    d.refresh_from_db()
    assert d.status == "retrying"


def test_a_delivery_stuck_in_sending_is_picked_up_again(ienv, http):
    d = delivery(ienv)
    Delivery.objects.filter(pk=d.pk).update(status="sending", attempts=0,
                                            last_attempt_at=timezone.now() - timedelta(minutes=30))
    assert tasks.retry_due() == 1
    d.refresh_from_db()
    assert d.status == "success"


def test_a_delivery_is_only_sent_by_one_worker(ienv, http):
    d = delivery(ienv)
    assert tasks.deliver(str(d.id)) == "skipped"             # already finished
    Delivery.objects.filter(pk=d.pk).update(status="sending")
    assert tasks.deliver(str(d.id)) == "skipped"             # someone else has it


def test_a_disabled_integration_fails_pending_deliveries(ienv, http):
    d = delivery(ienv)
    Delivery.objects.filter(pk=d.pk).update(status="retrying")
    Integration.objects.update(is_active=False)
    assert tasks.deliver(str(d.id)) == "failed"
    d.refresh_from_db()
    assert d.error == "integration_disabled"


def test_private_addresses_are_blocked_at_send_time_too(ienv, http, monkeypatch):
    d = delivery(ienv)
    monkeypatch.setattr(webhooks, "resolve", lambda host: ["169.254.169.254"])   # DNS changed
    Delivery.objects.filter(pk=d.pk).update(status="retrying")
    tasks.deliver(str(d.id))
    d.refresh_from_db()
    assert d.status == "failed" and d.error == "blocked_address"
    assert len(sent(http)) == 1                               # only the first, public, attempt


# ---------------------------------------------------------------- log, re-send, test button

def test_the_delivery_log_holds_no_customer_data(ienv, http):
    delivery(ienv, ref="LOG1")
    from django.forms.models import model_to_dict

    blob = json.dumps([model_to_dict(d) for d in Delivery.objects.all()], default=str)
    assert "Asha" not in blob and "9876543210" not in blob and "12 MG Road" not in blob


def test_the_delivery_list_filters_and_pages(ienv, http):
    i = make(ienv, booking_form_id(), event="booking.created")
    for n in range(3):
        create(ienv.ops, booking_id=f"P{n}")
    url = f"/api/v1/integrations/{i['id']}/deliveries"
    page = ienv.admin.get(url).json()
    assert page["count"] == 3 and page["results"][0]["booking_id"] == "P2"
    assert ienv.admin.get(url + "?status=failed").json()["count"] == 0
    assert ienv.admin.get(url + "?event=booking.created").json()["count"] == 3
    assert ienv.ops.get(url).status_code == 403


def test_resend_makes_a_new_delivery_from_todays_data(ienv, http):
    d = delivery(ienv, ref="RS1")
    r = ienv.admin.post(f"/api/v1/deliveries/{d.id}/resend")
    assert r.status_code == 202 and r.json()["resent_of"] == str(d.id)
    assert Delivery.objects.count() == 2 and len(sent(http)) == 2
    assert Delivery.objects.get(pk=r.json()["id"]).status == "success"
    assert ienv.ops.post(f"/api/v1/deliveries/{d.id}/resend").status_code == 403


def test_the_test_button_sends_a_ping_and_reports_the_result(ienv, http, booking):
    i = make(ienv, ienv.form_id, event="pdf.ready")
    r = ienv.admin.post(f"/api/v1/integrations/{i['id']}/test")
    assert r.status_code == 200 and r.json()["status"] == "success"
    assert r.json()["event"] == "test.ping"
    p = body_of(sent(http)[-1])
    assert p["event"] == "test.ping" and p["data"]["booking"]["booking_id"] == "SA37926"
    explicit = ienv.admin.post(f"/api/v1/integrations/{i['id']}/test",
                               {"booking": booking["id"]}, format="json")
    assert explicit.json()["booking"] == booking["id"]
    bad = ienv.admin.post(f"/api/v1/integrations/{i['id']}/test", {"booking": "nope"},
                          format="json")
    assert bad.status_code == 400
    assert ienv.ops.post(f"/api/v1/integrations/{i['id']}/test").status_code == 403


def test_the_test_button_without_any_booking_and_a_failing_endpoint(ienv):
    i = make(ienv, booking_form_id())
    with responses.RequestsMock() as r:
        r.add(responses.POST, HOOK, status=500)
        out = ienv.admin.post(f"/api/v1/integrations/{i['id']}/test").json()
    assert out["status"] == "failed" and out["error"] == "http_500"   # a test is not retried
    assert Delivery.objects.get().next_retry_at is None


def test_the_test_button_for_an_inspection_form_picks_that_types_booking(ienv, http, booking):
    i = make(ienv, ienv.form_id)
    out = ienv.admin.post(f"/api/v1/integrations/{i['id']}/test").json()
    assert out["booking"] == booking["id"]


def test_a_deleted_booking_still_delivers_its_ids(ienv, http, booking):
    make(ienv, booking_form_id(), event="booking.deleted")
    ienv.admin.delete(f"/api/v1/bookings/{booking['id']}")
    p = body_of(sent(http)[-1])
    assert p["booking"] == {"id": booking["id"], "booking_id": "SA37926"} and "data" not in p
    d = Delivery.objects.get()
    assert d.booking is None and d.booking_ref == "SA37926"


def test_events_for_a_booking_that_no_longer_exists_reach_booking_form_integrations(ienv, http):
    import uuid

    make(ienv, booking_form_id(), event="booking.deleted", include_data=True)
    make(ienv, ienv.form_id, name="insp", event="booking.deleted")
    gone = str(uuid.uuid4())
    events.emit("booking.deleted", booking=gone, booking_id="GONE1")
    assert [body_of(c)["booking"] for c in sent(http)] == [{"id": gone, "booking_id": "GONE1"}]


def test_the_connected_address_is_checked_so_dns_rebinding_cannot_reach_private_hosts(
        monkeypatch, settings):
    """check_url passes (DNS said 'public'), but the socket really connected to a private address."""
    from unittest import mock

    class FakeSocket:
        def __init__(self, ip):
            self.ip, self.closed = ip, False

        def getpeername(self):
            return (self.ip, 443)

        def close(self):
            self.closed = True

    for ip, blocked in (("10.1.2.3", True), ("169.254.169.254", True), ("93.184.216.34", False)):
        sock = FakeSocket(ip)
        with mock.patch("urllib3.connection.HTTPConnection._new_conn", return_value=sock):
            conn = webhooks.GuardedHTTPConnection("hooks.example.com", 80)
            if blocked:
                with pytest.raises(webhooks.BlockedAddress):
                    conn._new_conn()
                assert sock.closed
            else:
                assert conn._new_conn() is sock
    settings.WEBHOOK_ALLOW_PRIVATE = True
    with mock.patch("urllib3.connection.HTTPConnection._new_conn", return_value=FakeSocket("10.0.0.1")):
        assert webhooks.GuardedHTTPConnection("x", 80)._new_conn()
    with mock.patch("urllib3.connection.HTTPSConnection._new_conn", return_value=FakeSocket("10.0.0.1")):
        assert webhooks.GuardedHTTPSConnection("x", 443)._new_conn()
    assert webhooks.GuardedHTTPPool.ConnectionCls is webhooks.GuardedHTTPConnection
    assert webhooks.GuardedHTTPSPool.ConnectionCls is webhooks.GuardedHTTPSConnection


def test_a_connection_blocked_at_the_socket_fails_the_delivery_for_good(ienv, monkeypatch):
    with responses.RequestsMock() as r:
        r.add(responses.POST, HOOK, body=requests.ConnectionError("blocked_address"))
        d = delivery(ienv, ref="RB1")
    assert d.status == "failed" and d.error == "blocked_address" and d.next_retry_at is None


def test_the_session_uses_the_guarded_adapter():
    s = webhooks.session()
    assert isinstance(s.get_adapter("https://x.example.com"), webhooks.GuardedAdapter)
    adapter = s.get_adapter("https://x.example.com")
    assert isinstance(adapter, webhooks.GuardedAdapter)
    assert adapter.poolmanager.pool_classes_by_scheme["https"] is webhooks.GuardedHTTPSPool
