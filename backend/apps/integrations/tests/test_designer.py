"""The request designer: the picker's catalogue, {{ref}} values, method / URL / query / headers /
body, the preview, and warnings about values whose field has gone."""
import json
import re

import pytest
import responses

from apps.bookings.tests.conftest import create
from apps.bookings.tests.test_submissions import assign, start, submit
from apps.forms import services as form_services
from apps.forms.models import Field, Form, FormVersion, Section
from apps.integrations import values, webhooks
from apps.integrations.models import Delivery, Integration
from apps.media.models import MediaZip
from apps.reports.tests.test_reports import renv  # noqa: F401

from .conftest import HOOK, booking_form_id, make

pytestmark = pytest.mark.django_db

ANY_HOOK = re.compile(r"https://hooks\.example\.com/.*")


@pytest.fixture
def anyhttp():
    """Any method, any path on the hook host answers 200."""
    with responses.RequestsMock(assert_all_requests_are_fired=False) as r:
        for method in (responses.POST, responses.PUT, responses.PATCH, responses.GET,
                       responses.DELETE):
            r.add(method, ANY_HOOK, status=200, body="ok")
        yield r


def calls(http):
    return [c for c in http.calls if c.request.url.startswith("https://hooks.example.com")]


def refs(client, form_id, event):
    r = client.get(f"/api/v1/integrations/catalogue?form={form_id}&event={event}")
    assert r.status_code == 200, r.json()
    return {e["ref"]: e for e in r.json()}


def submitted(ienv, booking):
    assign(ienv, booking)
    start(ienv.expert, booking)
    submit(ienv.expert, booking)


# ---------------------------------------------------------------- the picker's list (T1.2)

def test_the_catalogue_groups_values_and_gives_each_a_type(ienv):
    got = refs(ienv.admin, ienv.form_id, "pdf.ready")
    assert got["booking.customer_name"]["group"] == "booking"
    assert got["inspection.odometer"]["type"] == "number"
    assert got["inspection.grade"]["type"] == "number"          # a rating
    assert got["inspection.door"]["group"] == "inspection"
    assert got["job.booking_id"]["label"] == "Booking ID"
    assert got["result.rating.engine"]["type"] == "number"
    assert got["result.key_checks"]["type"] == "list"
    assert got["link.pdf"]["group"] == "link"
    assert got["link.photos.door_photo"]["type"] == "list"
    assert "inspection.door_photo" not in got                   # a photo is a link, not a value
    assert {"event.name", "event.delivery", "event.time"} <= set(got)


@pytest.mark.parametrize("event,present,absent", [
    ("booking.created", {"booking.city", "job.booking_id", "event.name"},
     {"inspection.odometer", "result.overall", "link.pdf", "link.image_zip", "start.selfie"}),
    ("booking.updated", {"inspection.odometer", "link.pdf", "event.changed_fields",
                         "link.image_zip"}, {"event.alert"}),
    ("booking.deleted", {"job.booking_id", "event.name", "event.delivery", "event.time"},
     {"booking.city", "job.city", "inspection.odometer", "job.id"}),
    ("inspection.started", {"booking.city", "job.type"},
     {"inspection.odometer", "result.overall", "link.pdf"}),
    ("inspection.submitted", {"inspection.odometer", "result.overall", "link.photos.door_photo"},
     {"link.pdf", "link.image_zip"}),
    ("media.completed", {"inspection.odometer", "link.image_zip", "link.video_zip"},
     {"link.pdf"}),
    ("pdf.ready", {"inspection.odometer", "link.pdf", "link.image_zip"}, set()),
    ("alert.conflict", {"booking.city", "event.alert"}, {"inspection.odometer", "link.pdf"}),
    ("alert.stuck_upload", {"booking.city", "event.alert"}, {"inspection.odometer"}),
])
def test_the_catalogue_hides_what_an_event_can_never_have(ienv, event, present, absent):
    got = set(refs(ienv.admin, ienv.form_id, event))
    assert present <= got
    assert not absent & got


def test_a_booking_form_integration_is_offered_booking_values_only(ienv):
    got = refs(ienv.admin, booking_form_id(), "booking.updated")
    assert {"booking.customer_name", "job.booking_id", "job.previous_booking_id",
            "event.changed_fields"} <= set(got)
    assert not {r for r in got if r.split(".")[0] in ("inspection", "start", "end", "result",
                                                      "link")}


def test_the_catalogue_lists_the_latest_published_version_only(ienv):
    form = Form.objects.get(pk=ienv.form_id)
    draft = form_services.create_draft(ienv.admin_user, form)
    section = Section.objects.filter(version=draft).first()
    assert section is not None
    Field.objects.create(version=draft, section=section,
                         key="draft_only", label="Draft only", type="short_text")
    assert "inspection.draft_only" not in refs(ienv.admin, ienv.form_id, "pdf.ready")


def test_the_catalogue_endpoint_checks_its_input_and_the_role(ienv):
    url = "/api/v1/integrations/catalogue"
    assert ienv.admin.get(f"{url}?form=999999&event=pdf.ready").json()["code"] == "INVALID_FORM"
    assert ienv.admin.get(f"{url}?form={ienv.form_id}&event=nope").json()["code"] == \
        "INVALID_EVENT"
    assert ienv.admin.get(f"{url}?event=pdf.ready").status_code == 400
    assert ienv.ops.get(f"{url}?form={ienv.form_id}&event=pdf.ready").status_code == 403


# ---------------------------------------------------------------- filling values (T1.3)

def test_a_single_value_keeps_its_type_and_mixed_text_is_text():
    get = {"a.n": 2019, "a.b": True, "a.l": ["Petrol", "CNG"], "a.e": "", "a.x": None,
           "a.t": "x y"}.get
    assert values.render("{{a.n}}", get) == 2019
    assert values.render("{{ a.b }}", get) is True
    assert values.render("{{a.l}}", get) == ["Petrol", "CNG"]
    assert values.render("{{a.e}}", get) is None and values.render("{{a.x}}", get) is None
    assert values.render("{{a.n}}", get, as_text=True) == "2019"             # force text
    assert values.render("{{a.b}}", get, as_text=True) == "Yes"
    assert values.render("{{a.x}}", get, as_text=True) is None
    assert values.render("Year {{a.n}}: {{a.b}}", get) == "Year 2019: Yes"
    assert values.render("{{a.l}}!", get) == "Petrol, CNG!"
    assert values.render("{{a.l}}", get, as_text=True, sep=",") == "Petrol,CNG"
    assert values.render("plain", get) == "plain"
    assert values.render("/leads/{{a.t}}", get, encode=True) == "/leads/x%20y"
    with pytest.raises(values.MissingPathValue):
        values.render("/leads/{{a.x}}", get, encode=True)
    assert values.check_syntax("a {{ x.y }} b") and not values.check_syntax("{{ x")
    assert not values.check_syntax("x }}")
    assert values.text_of({"a": 1}) == '{"a":1}' and values.text_of(None) == ""


def test_a_custom_body_is_built_from_the_job(ienv, http, booking):
    make(ienv, ienv.form_id, event="inspection.submitted", body_mode="custom", body={
        "ref": "{{job.booking_id}}", "odo": "{{inspection.odometer}}",
        "odo_text": "{{ inspection.odometer | text }}",
        "line": "{{booking.customer_name}} drove {{inspection.odometer}} km",
        "earlier": "{{job.previous_booking_id}}",
        "fixed_n": 7, "fixed_b": True, "fixed_t": "x", "fixed_null": None,
        "car": {"city": "{{booking.city}}", "door": "{{inspection.door}}"},
        "list": ["{{booking.city}}", 3, {"deep": "{{event.name}}"}],
        "overall": "{{result.overall}}", "ratings": "{{result.ratings}}",
        "checks": "{{result.key_checks}}", "event": "{{event.name}}",
        "id": "{{event.delivery}}"})
    submitted(ienv, booking)
    body = json.loads(calls(http)[-1].request.body)
    assert body["ref"] == "SA37926" and body["odo"] == 45 and body["odo_text"] == "45"
    assert body["line"] == "Asha drove 45 km" and body["earlier"] is None
    assert body["fixed_n"] == 7 and body["fixed_b"] is True and body["fixed_t"] == "x"
    assert body["fixed_null"] is None
    assert body["list"] == ["delhi", 3, {"deep": "inspection.submitted"}]
    assert body["car"] == {"city": "delhi", "door": "ok"}
    assert body["overall"] and isinstance(body["ratings"], list) and body["checks"] == []
    assert body["event"] == "inspection.submitted" and body["id"]
    assert "data" not in body                                   # custom: only what is mapped


def test_results_use_the_final_ratings_after_ops_changes(ienv, http, booking):
    make(ienv, ienv.form_id, event="inspection.submitted", body_mode="custom", body={
        "engine": "{{result.rating.engine}}", "ratings": "{{result.ratings}}"})
    submitted(ienv, booking)
    insp = booking_inspection(booking)
    insp.overrides = {"ratings": {"engine": 2}}
    insp.save()
    from apps.scoring.service import recompute

    recompute(insp)
    d = Delivery.objects.create(integration=Integration.objects.get(),
                                event="inspection.submitted", booking_id=booking["id"],
                                booking_uuid=booking["id"], booking_ref="SA37926")
    webhooks.attempt(d)
    body = json.loads(calls(http)[-1].request.body)
    assert body["engine"] == 2 and body["ratings"] == [{"category": "Engine", "rating": 2}]


def booking_inspection(booking):
    from apps.bookings.models import Inspection

    return Inspection.objects.get(booking_id=booking["id"])


def test_a_previous_booking_id_is_filled_after_an_id_edit(ienv, anyhttp, booking):
    make(ienv, booking_form_id(), event="booking.updated", method="PUT",
         url="https://hooks.example.com/leads/{{job.previous_booking_id}}",
         headers=[{"key": "X-Now", "value": "{{job.booking_id}}"}],
         query=[{"key": "changed", "value": "{{event.changed_fields}}"}])
    b = ienv.ops.get(f"/api/v1/bookings/{booking['id']}").json()
    ienv.ops.patch(f"/api/v1/bookings/{booking['id']}", {
        "row_version": b["row_version"],
        "answers": {"booking_id": "SA99999", "customer_name": "Someone Else"}}, format="json")
    r = calls(anyhttp)[-1].request
    assert r.method == "PUT"
    assert r.url == "https://hooks.example.com/leads/SA37926?changed=booking_id%2Ccustomer_name"
    assert r.headers["X-Now"] == "SA99999"


def test_a_deleted_booking_sends_only_its_id_and_the_event(ienv, anyhttp, booking):
    make(ienv, booking_form_id(), event="booking.deleted", method="DELETE",
         url="https://hooks.example.com/leads/{{job.booking_id}}")
    # the picker does not offer more, and a value saved earlier still gets nothing for it
    r = ienv.admin.post("/api/v1/integrations", {
        "form": booking_form_id(), "name": "x", "url": HOOK, "event": "booking.deleted",
        "headers": [{"key": "X-City", "value": "{{booking.city}}"}]}, format="json")
    assert r.json()["code"] == "UNKNOWN_VALUE"
    Integration.objects.create(
        form_id=booking_form_id(), name="body", event="booking.deleted", url=HOOK,
        headers=[{"key": "X-City", "value": "{{booking.city}}"}], body_mode="custom",
        body={"ref": "{{job.booking_id}}", "city": "{{booking.city}}",
              "event": "{{event.name}}"})
    ienv.admin.delete(f"/api/v1/bookings/{booking['id']}")
    by_method = {c.request.method: c.request for c in calls(anyhttp)}
    assert by_method["DELETE"].url == "https://hooks.example.com/leads/SA37926"
    assert "X-City" not in by_method["POST"].headers            # nothing of a deleted booking
    assert json.loads(by_method["POST"].body) == {"ref": "SA37926", "city": None,
                                                  "event": "booking.deleted"}


# ---------------------------------------------------------------- the request (T1.4)

@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH"])
def test_these_methods_carry_the_json_body(ienv, anyhttp, method):
    make(ienv, booking_form_id(), method=method, headers=[{"key": "Authorization",
                                                           "value": "Bearer abc"}])
    create(ienv.ops, booking_id="M1")
    r = calls(anyhttp)[-1].request
    assert r.method == method and r.headers["Content-Type"] == "application/json"
    assert r.headers["Authorization"] == "Bearer abc"
    assert json.loads(r.body)["event"] == "booking.created"
    assert r.headers["X-Vayu-Event"] == "booking.created" and r.headers["User-Agent"]
    assert "X-Vayu-Signature" not in r.headers                  # no signing any more


@pytest.mark.parametrize("method", ["GET", "DELETE"])
def test_get_and_delete_have_no_body(ienv, anyhttp, method):
    make(ienv, booking_form_id(), method=method,
         url="https://hooks.example.com/leads/{{job.booking_id}}")
    create(ienv.ops, booking_id="M2")
    r = calls(anyhttp)[-1].request
    assert r.method == method and r.body is None and "Content-Type" not in r.headers
    assert r.url == "https://hooks.example.com/leads/M2"
    assert Delivery.objects.get(booking_ref="M2").status == "success"


def test_values_in_the_path_are_url_encoded(ienv, anyhttp):
    make(ienv, booking_form_id(), url="https://hooks.example.com/leads/{{job.booking_id}}/x")
    create(ienv.ops, booking_id="A B/7")
    assert calls(anyhttp)[-1].request.url == "https://hooks.example.com/leads/A%20B%2F7/x"


def test_an_empty_path_value_fails_the_delivery_for_good(ienv, anyhttp):
    make(ienv, booking_form_id(), url="https://hooks.example.com/leads/{{job.previous_booking_id}}")
    create(ienv.ops, booking_id="M3")
    d = Delivery.objects.get(booking_ref="M3")
    assert d.status == "failed" and d.error == "missing_path_value" and d.next_retry_at is None
    assert calls(anyhttp) == []


def test_empty_query_and_header_values_are_left_out_and_lists_are_joined(ienv, anyhttp, booking):
    make(ienv, booking_form_id(), url="https://hooks.example.com/x?fixed=1", event="booking.updated",
         query=[{"key": "src", "value": "vayu"}, {"key": "city", "value": "{{booking.city}}"},
                {"key": "old", "value": "{{job.previous_booking_id}}"},
                {"key": "who", "value": "{{booking.customer_name}} from {{booking.city}}"}],
         headers=[{"key": "X-City", "value": "{{booking.city}}"},
                  {"key": "X-Old", "value": "{{job.previous_booking_id}}"}])
    assign(ienv, booking)
    r = calls(anyhttp)[-1].request
    assert r.url == "https://hooks.example.com/x?fixed=1&src=vayu&city=delhi&who=Asha+from+delhi"
    assert r.headers["X-City"] == "delhi" and "X-Old" not in r.headers


def test_a_multi_line_answer_in_a_header_becomes_one_line(ienv, anyhttp):
    make(ienv, booking_form_id(), headers=[{"key": "X-Addr", "value": "{{booking.address}}"}])
    create(ienv.ops, booking_id="M4", address="12 MG Road\nSector 4\r\nDelhi")
    r = calls(anyhttp)[-1].request
    assert r.headers["X-Addr"] == "12 MG Road Sector 4 Delhi"
    assert Delivery.objects.get(booking_ref="M4").status == "success"      # not retried six times


def test_a_non_latin_answer_in_a_header_is_percent_encoded_and_the_send_succeeds(ienv, anyhttp):
    make(ienv, booking_form_id(), headers=[{"key": "X-Who", "value": "{{booking.customer_name}}"}])
    create(ienv.ops, booking_id="M7", customer_name="आशा Verma")
    value = calls(anyhttp)[-1].request.headers["X-Who"]
    assert value == "%E0%A4%86%E0%A4%B6%E0%A4%BE Verma"
    value.encode("latin-1")                                     # what http.client needs
    assert Delivery.objects.get(booking_ref="M7").status == "success"


def test_an_unexpected_error_while_sending_fails_the_delivery_instead_of_leaving_it_sending(
        ienv, monkeypatch):
    class Broken:
        def __enter__(self):
            raise UnicodeError("boom")

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(webhooks, "session", lambda: Broken())
    make(ienv, booking_form_id())
    create(ienv.ops, booking_id="M8")
    d = Delivery.objects.get(booking_ref="M8")
    assert d.status == "failed" and d.error == "request_failed" and d.attempts == 1


def test_a_preview_that_would_be_too_large_says_so(ienv, booking, monkeypatch):
    monkeypatch.setattr(webhooks, "MAX_BODY", 5)
    r = preview(ienv.admin, booking_form_id())
    assert r.status_code == 400 and r.json()["code"] == "REQUEST_FAILED"


def test_the_test_button_uses_a_job_with_a_submission_like_the_preview(ienv, anyhttp, booking):
    submitted(ienv, booking)
    newer = create(ienv.ops, booking_id="NEWER2").json()           # newest, but nothing to send yet
    i = make(ienv, ienv.form_id, event="inspection.submitted", method="PUT",
             url="https://hooks.example.com/leads/{{job.booking_id}}")
    out = ienv.admin.post(f"/api/v1/integrations/{i['id']}/test").json()
    assert out["booking"] == booking["id"] and out["booking"] != newer["id"]
    assert calls(anyhttp)[-1].request.url == "https://hooks.example.com/leads/SA37926"


def test_the_address_check_runs_on_the_final_url(ienv, anyhttp, monkeypatch):
    make(ienv, booking_form_id(), url="https://hooks.example.com/leads/{{job.booking_id}}")
    monkeypatch.setattr(webhooks, "resolve", lambda host: ["10.0.0.5"])       # DNS changed
    create(ienv.ops, booking_id="M5")
    assert Delivery.objects.get(booking_ref="M5").error == "blocked_address"
    assert calls(anyhttp) == []


def test_a_body_that_cannot_be_built_fails_without_retrying(ienv, anyhttp, monkeypatch):
    monkeypatch.setattr(webhooks, "MAX_BODY", 5)
    make(ienv, booking_form_id())
    create(ienv.ops, booking_id="M6")
    d = Delivery.objects.get(booking_ref="M6")
    assert d.status == "failed" and d.error == "request_failed" and d.attempts == 1


def test_the_test_button_marks_its_request_and_sends_real_values(ienv, anyhttp, booking):
    i = make(ienv, booking_form_id(), method="PUT",
             url="https://hooks.example.com/leads/{{job.booking_id}}")
    out = ienv.admin.post(f"/api/v1/integrations/{i['id']}/test").json()
    r = calls(anyhttp)[-1].request
    assert out["status"] == "success" and r.url == "https://hooks.example.com/leads/SA37926"
    assert r.headers["X-Vayu-Test"] == "1" and r.headers["X-Vayu-Event"] == "test.ping"


def test_editing_keeps_valid_values_and_a_toggle_never_needs_a_recheck(ienv):
    i = make(ienv, ienv.form_id, event="pdf.ready", body_mode="custom",
             body={"pdf": "{{link.pdf}}"},
             query=[{"key": "a", "value": "{{booking.city}}"}])
    # changing the event re-checks every value against the new event's list
    r = ienv.admin.patch(f"/api/v1/integrations/{i['id']}", {"event": "booking.updated"},
                         format="json")
    assert r.status_code == 200 and r.json()["event"] == "booking.updated"
    r = ienv.admin.patch(f"/api/v1/integrations/{i['id']}", {"event": "inspection.started"},
                         format="json")
    assert r.json()["code"] == "UNKNOWN_VALUE"                  # link.pdf is not offered there
    assert ienv.admin.patch(f"/api/v1/integrations/{i['id']}", {"is_active": False},
                            format="json").status_code == 200


# ---------------------------------------------------------------- the preview (T1.5)

def preview(client, form, **over):
    body = {"form": form, "url": HOOK, "event": "booking.created", **over}
    return client.post("/api/v1/integrations/preview", body, format="json")


def test_the_preview_shows_the_whole_request_for_a_real_job(ienv, booking):
    r = preview(ienv.admin, booking_form_id(), method="PATCH", event="booking.updated",
                url="https://hooks.example.com/leads/{{job.booking_id}}",
                query=[{"key": "c", "value": "{{booking.city}}"}],
                headers=[{"key": "Authorization", "value": "Bearer abc"}],
                body_mode="custom", body={"ref": "{{job.booking_id}}", "n": 3})
    out = r.json()
    assert r.status_code == 200 and out["sample"] is False and out["booking"] == booking["id"]
    assert out["method"] == "PATCH"
    assert out["url"] == "https://hooks.example.com/leads/SA37926?c=delhi"
    names = {h["name"]: h["value"] for h in out["headers"]}
    assert names["Authorization"] == "Bearer abc" and names["Content-Type"] == "application/json"
    assert json.loads(out["body"]) == {"ref": "SA37926", "n": 3} and "\n" in out["body"]


def test_the_preview_works_before_the_integration_has_a_name(ienv, booking):
    assert preview(ienv.admin, booking_form_id(), name="").status_code == 200
    assert preview(ienv.admin, booking_form_id(), name="x" * 200).status_code == 400


def test_the_preview_sends_nothing_saves_nothing_and_builds_no_zip(ienv, booking, anyhttp):
    submitted(ienv, booking)
    before = Delivery.objects.count()
    r = preview(ienv.admin, ienv.form_id, event="media.completed", include_image_zip=True,
                include_video_zip=True)
    assert "/zip/" in r.json()["body"]
    r = preview(ienv.admin, ienv.form_id, event="media.completed", body_mode="custom",
                body={"z": "{{link.image_zip}}"})
    assert "/zip/" in r.json()["body"]
    assert Delivery.objects.count() == before and MediaZip.objects.count() == 0
    assert calls(anyhttp) == []


def test_the_preview_needs_no_dns_and_is_admin_only(ienv, booking, monkeypatch):
    def nxdomain(host):
        raise OSError("nope")

    monkeypatch.setattr(webhooks, "resolve", nxdomain)
    assert preview(ienv.admin, booking_form_id()).status_code == 200
    assert preview(ienv.ops, booking_form_id()).status_code == 403
    assert preview(ienv.admin, booking_form_id(), url="ftp://x").status_code == 400
    assert preview(ienv.admin, booking_form_id(), event="pdf.ready").status_code == 400


@pytest.mark.parametrize("event", webhooks.EVENTS)
@pytest.mark.parametrize("mode", ["standard", "custom"])
def test_the_preview_works_for_every_event_with_a_job_or_without(ienv, booking, event, mode):
    from apps.bookings.models import Booking

    body = {"ref": "{{job.booking_id}}", "name": "{{event.name}}"}
    for have_job in (True, False):
        if not have_job:
            Booking.objects.all().delete()
        out = preview(ienv.admin, ienv.form_id, event=event, body_mode=mode, body=body,
                      include_pdf=True, include_image_zip=True).json()
        assert out["sample"] is (not have_job) and out["method"] == "POST"
        parsed = json.loads(out["body"])
        if mode == "custom":
            assert parsed["name"] == event
            assert parsed["ref"] == ("SA37926" if have_job else "SAMPLE-001") or \
                event == "booking.deleted"
        else:
            assert parsed["event"] == event


def test_a_form_without_jobs_previews_with_sample_values(ienv):
    out = preview(ienv.admin, ienv.form_id, event="pdf.ready", body_mode="custom", body={
        "odo": "{{inspection.odometer}}", "name": "{{booking.customer_name}}",
        "ok": "{{inspection.grade}}", "links": "{{link.photos.door_photo}}"}).json()
    assert out["sample"] is True and out["booking"] is None
    assert json.loads(out["body"]) == {"odo": 42, "name": "sample", "ok": 42,
                                       "links": ["sample 1", "sample 2"]}
    std = preview(ienv.admin, ienv.form_id, event="pdf.ready", include_pdf=True,
                  fields=["odometer"]).json()
    data = json.loads(std["body"])
    assert data["data"]["inspection"] == {"odometer": 42} and "pdf_url" in data
    assert "start" not in data["data"]


def test_the_preview_prefers_a_job_that_has_a_submission(ienv, booking):
    submitted(ienv, booking)
    newer = create(ienv.ops, booking_id="NEWER").json()
    assert preview(ienv.admin, ienv.form_id, event="inspection.submitted").json()["booking"] == \
        booking["id"]
    assert preview(ienv.admin, ienv.form_id, event="inspection.submitted",
                   booking=newer["id"]).json()["booking"] == newer["id"]
    assert preview(ienv.admin, ienv.form_id, booking="nope").status_code == 400


def test_an_empty_path_value_is_explained_in_the_preview(ienv, booking):
    r = preview(ienv.admin, booking_form_id(), event="booking.updated",
                url="https://hooks.example.com/{{job.previous_booking_id}}")
    assert r.status_code == 400 and r.json()["code"] == "PATH_VALUE_EMPTY"


def test_the_standard_body_keeps_working_with_its_checklist(ienv, anyhttp, booking):
    make(ienv, ienv.form_id, event="inspection.submitted", fields=["odometer", "city"])
    submitted(ienv, booking)
    data = json.loads(calls(anyhttp)[-1].request.body)["data"]
    assert data == {"booking": {"city": "delhi"}, "inspection": {"odometer": 45}}


# ---------------------------------------------------------------- fields that disappear (T1.6)

def drop_field_and_publish(ienv, key):
    form = Form.objects.get(pk=ienv.form_id)
    draft = form_services.create_draft(ienv.admin_user, form)
    Field.objects.filter(version=draft, key=key).delete()
    draft = FormVersion.objects.get(pk=draft.pk)
    r = ienv.admin.post(f"/api/v1/form-versions/{draft.id}/publish",
                        {"row_version": draft.row_version}, format="json")
    assert r.status_code == 200, r.json()
    return r.json()


def test_a_removed_field_is_warned_on_publish_listed_on_the_integration_and_sends_null(
        ienv, http, booking):
    i = make(ienv, ienv.form_id, event="inspection.submitted", fields=["odometer"],
             body_mode="custom", body={"odo": "{{inspection.odometer}}",
                                       "city": "{{booking.city}}"})
    assert i["broken_refs"] == []
    standard = make(ienv, ienv.form_id, name="std", event="inspection.submitted",
                    fields=["odometer"])
    make(ienv, ienv.form_id, name="plain", event="pdf.ready")             # uses no field at all
    published = drop_field_and_publish(ienv, "odometer")
    warned = {w["name"]: w for w in published["warnings"]
              if w["code"] == "INTEGRATION_FIELD_MISSING"}
    assert warned["ERP"]["keys"] == ["inspection.odometer"]
    assert warned["std"]["keys"] == ["field.odometer"]
    got = ienv.admin.get(f"/api/v1/integrations/{i['id']}").json()
    assert got["broken_refs"] == ["inspection.odometer"]
    assert ienv.admin.get(f"/api/v1/integrations/{standard['id']}").json()["broken_refs"] == \
        ["field.odometer"]
    assign(ienv, booking)
    start(ienv.expert, booking)
    submit(ienv.expert, booking, answers={"inspection": {"chassis_no": "MA3YPKCSKTJ273129",
                                                         "door": "ok"}})
    body = next(b for b in (json.loads(c.request.body) for c in calls_to(http)) if "odo" in b)
    assert body["odo"] is None and body["city"] == "delhi"               # a missing value is null
    # an existing broken value does not stop a toggle, but a new save must fix it
    assert ienv.admin.patch(f"/api/v1/integrations/{i['id']}", {"is_active": False},
                            format="json").status_code == 200
    assert ienv.admin.patch(f"/api/v1/integrations/{i['id']}", {"name": "x", "url": HOOK},
                            format="json").json()["code"] == "UNKNOWN_VALUE"


def calls_to(http):
    return [c for c in http.calls if c.request.url == HOOK]


def test_publishing_without_breaking_anything_warns_about_nothing(ienv):
    make(ienv, ienv.form_id, event="pdf.ready", body_mode="custom",
         body={"odo": "{{inspection.odometer}}"})
    published = drop_field_and_publish(ienv, "door_photo")
    assert [w for w in published["warnings"] if w["code"] == "INTEGRATION_FIELD_MISSING"] == []


def test_an_already_broken_integration_is_not_blamed_on_the_next_publish(ienv):
    from apps.integrations.models import Integration

    i = make(ienv, ienv.form_id, event="pdf.ready", body_mode="custom",
             body={"odo": "{{inspection.odometer}}"})
    drop_field_and_publish(ienv, "odometer")
    assert values.broken_refs(Integration.objects.get(pk=i["id"])) == ["inspection.odometer"]
    again = drop_field_and_publish(ienv, "door_photo")
    assert [w for w in again["warnings"] if w["code"] == "INTEGRATION_FIELD_MISSING"] == []


# ---------------------------------------------------------------- every value, with a finished job

def test_every_kind_of_value_resolves_for_a_finished_job(renv, http, settings):
    from apps.reports.tests.test_reports import complete_job, set_template

    rows = {ref.replace(".", "_"): "{{" + ref + "}}" for ref in (
        "link.pdf", "link.image_zip", "link.video_zip", "link.photos.photo_a",
        "result.overall", "result.average", "result.defects", "result.ratings",
        "result.key_checks", "result.rating.engine", "inspection.engine_rating",
        "inspection.dents", "inspection.door", "inspection.odometer", "job.id", "job.type",
        "job.stage", "job.city", "job.expert", "job.created_at", "job.submitted_at",
        "job.revision", "event.time", "booking.customer_name")}
    make(renv, renv.form_id, event="pdf.ready", body_mode="custom", body=rows)
    set_template(renv)
    b = complete_job(renv, settings=settings)
    body = json.loads(calls_to(http)[-1].request.body)
    assert body["link_pdf"].startswith("https://") and "X-Amz-Expires=604800" in body["link_pdf"]
    assert "/zip/" in body["link_image_zip"] and body["link_video_zip"] is None
    assert len(body["link_photos_photo_a"]) == 2
    assert body["result_overall"] and body["result_average"] is not None
    assert body["result_defects"] == ["inspection.door"]
    assert body["result_ratings"][0]["category"] == "Engine"
    assert body["result_key_checks"] == [{"name": "dents", "result": True}]
    assert body["result_rating_engine"] == body["result_ratings"][0]["rating"]
    assert body["inspection_engine_rating"] == body["result_rating_engine"]
    assert body["inspection_dents"] is True and body["inspection_door"] == "dent"
    assert body["inspection_odometer"] == 45
    assert body["job_id"] == b["id"] and body["job_type"] == "pdi" and body["job_stage"]
    assert body["job_city"] == "delhi" and body["job_created_at"] and body["job_submitted_at"]
    assert "job_revision" in body and body["event_time"]
    assert body["booking_customer_name"] == "Asha"
    assert body["job_expert"]


def test_values_that_do_not_exist_yet_are_null(ienv, anyhttp, booking):
    make(ienv, ienv.form_id, event="booking.updated", body_mode="custom", body={
        "odo": "{{inspection.odometer}}", "overall": "{{result.overall}}",
        "pdf": "{{link.pdf}}", "who": "{{job.expert}}", "at": "{{job.submitted_at}}"})
    assign(ienv, booking)
    body = json.loads(calls_to(anyhttp)[-1].request.body)
    assert body["odo"] is None and body["overall"] is None and body["pdf"] is None
    assert body["at"] is None and body["who"]
    start(ienv.expert, booking)                                 # a draft: still no results
    body = json.loads(calls_to(anyhttp)[-1].request.body)
    assert body["overall"] is None


def test_a_gps_answer_becomes_text_and_unknown_refs_give_nothing(ienv, anyhttp, booking):
    submitted(ienv, booking)
    insp = booking_inspection(booking)
    insp.answers = {**insp.answers, "inspection": {**insp.answers["inspection"],
                                                   "odometer": {"lat": 28.6, "lng": 77.2}}}
    insp.save()
    Field.objects.filter(key="odometer").update(type="gps")
    d = Delivery(integration=Integration(form_id=ienv.form_id), event="pdf.ready",
                 booking_uuid=booking["id"], booking_ref="SA37926")
    r = values.Resolver(d)
    assert r.get("inspection.odometer") == "28.6,77.2"
    assert r.get("zzz.x") is None and r.get("result.zzz") is None and r.get("link.zzz") is None
    assert r.get("job.zzz") is None


def test_the_preview_makes_a_sample_for_every_kind_of_value(ienv):
    entries = refs(ienv.admin, ienv.form_id, "pdf.ready")
    rows = {ref.replace(".", "_"): "{{" + ref + "}}" for ref in entries}
    out = preview(ienv.admin, ienv.form_id, event="pdf.ready", body_mode="custom",
                  body=rows).json()
    got = json.loads(out["body"])
    assert out["sample"] is True and len(got) == len(entries)
    types = {e["type"] for e in entries.values()}
    assert {"text", "number", "boolean", "date", "datetime", "list"} >= types
    assert {"number", "list", "datetime", "text"} <= types
    assert got["job_booking_id"] == "SAMPLE-001"
    # a boolean and a date exist in the booking / finished-job lists too
    assert values.sample("boolean", "x") is True and values.sample("date", "x") == "2026-01-15"
    assert values.sample("datetime", "x").startswith("2026-01-15T")


def test_the_standard_sample_body_without_data_has_only_the_basics(ienv):
    out = preview(ienv.admin, ienv.form_id, event="pdf.ready", include_data=False).json()
    assert set(json.loads(out["body"])) == {"event", "delivery", "occurred_at", "booking"}


@pytest.mark.parametrize("change", [
    {"url": "https://hooks.example.com/{{job.booking_id}}", "query": [{"key": "a", "value": 5}]},
    {"body_mode": "custom", "body": "x"},
    {"body_mode": "custom", "body": {f"k{i}": 1 for i in range(values.MAX_NODES + 1)}},
    {"headers": [{"key": f"H{i}", "value": "x"} for i in range(21)]},
    {"headers": "x"},
])
def test_oversized_or_malformed_designs_are_refused(ienv, change):
    r = ienv.admin.post("/api/v1/integrations", {"form": booking_form_id(), "name": "x",
                                                 "url": HOOK, "event": "booking.created",
                                                 **change}, format="json")
    assert r.status_code == 400


def test_a_body_nested_too_deeply_is_refused(ienv):
    body: dict | list = {"leaf": 1}
    for _ in range(values.MAX_DEPTH + 1):
        body = [body]
    r = ienv.admin.post("/api/v1/integrations", {
        "form": booking_form_id(), "name": "x", "url": HOOK, "event": "booking.created",
        "body_mode": "custom", "body": body}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "INVALID_BODY"


# ---------------------------------------------------------------- the JSON body, the form, the checklist

def test_an_old_row_body_becomes_the_json_it_described():
    import importlib

    m = importlib.import_module("apps.integrations.migrations.0003_json_body")
    rows = [{"key": "ref", "value": "{{job.booking_id}}"},
            {"key": "odo", "value": " {{ inspection.odometer }} ", "as_text": True},
            {"key": "mixed", "value": "a {{x.y}} b", "as_text": True}, {"key": "n", "fixed": 3},
            {"key": "car", "rows": [{"key": "city", "value": "{{booking.city}}"}]}]
    assert m.rows_to_json(rows) == {
        "ref": "{{job.booking_id}}", "odo": "{{ inspection.odometer | text}}",
        "mixed": "a {{x.y}} b", "n": 3, "car": {"city": "{{booking.city}}"}}
    from django.apps import apps

    old = Integration.objects.create(form_id=booking_form_id(), name="old", event="booking.created",
                                     url=HOOK, body_mode="custom", body={"rows": rows[:1]})
    std = Integration.objects.create(form_id=booking_form_id(), name="std", event="booking.created",
                                     url=HOOK, body_mode="standard", body={})
    m.to_json(apps, None)
    old.refresh_from_db()
    std.refresh_from_db()
    assert old.body == {"ref": "{{job.booking_id}}"} and std.body == {}


def test_a_body_can_be_any_json_list_or_object_and_text_can_be_forced(ienv, anyhttp):
    make(ienv, booking_form_id(), method="PUT", body_mode="custom",
         body=[{"city": "{{booking.city | text}}"}, "{{booking.city}}", 5, None])
    create(ienv.ops, booking_id="J1")
    assert json.loads(calls(anyhttp)[-1].request.body) == [{"city": "delhi"}, "delhi", 5, None]


def test_the_catalogue_without_an_event_lists_everything_for_the_checklist(ienv):
    got = set(refs_all(ienv.admin, ienv.form_id))
    assert {"booking.city", "inspection.odometer", "link.pdf", "event.alert"} <= got
    assert "inspection.odometer" not in refs(ienv.admin, ienv.form_id, "booking.created")


def refs_all(client, form_id):
    r = client.get(f"/api/v1/integrations/catalogue?form={form_id}")
    assert r.status_code == 200, r.json()
    return {e["ref"]: e for e in r.json()}


def test_the_form_of_an_integration_can_be_changed_with_its_event(ienv):
    i = make(ienv, ienv.form_id, event="pdf.ready", body_mode="custom",
             body={"pdf": "{{link.pdf}}"})
    bad = ienv.admin.patch(f"/api/v1/integrations/{i['id']}", {"form": booking_form_id()},
                           format="json")
    assert bad.json()["code"] == "INVALID_EVENT"                 # a booking form has no pdf.ready
    bad = ienv.admin.patch(f"/api/v1/integrations/{i['id']}", {
        "form": booking_form_id(), "event": "booking.updated"}, format="json")
    assert bad.json()["code"] == "UNKNOWN_VALUE"                 # and no PDF link: the body is checked
    ok = ienv.admin.patch(f"/api/v1/integrations/{i['id']}", {
        "form": booking_form_id(), "event": "booking.updated", "body": {"c": "{{booking.city}}"}},
        format="json")
    assert ok.status_code == 200 and ok.json()["form"] == booking_form_id()


def test_a_list_works_out_each_forms_field_keys_once(ienv):
    """Two standard integrations of one form share the list's cache (F-089)."""
    from unittest import mock

    for name in ("std1", "std2"):
        make(ienv, ienv.form_id, name=name, event="inspection.submitted", fields=["odometer"])
    cache: dict = {}
    with mock.patch.object(values, "versions", wraps=values.versions) as spy:
        out = [values.broken_refs(i, cache=cache)
               for i in Integration.objects.filter(form_id=ienv.form_id, name__in=["std1", "std2"])]
    assert out == [[], []]
    assert spy.call_count == 2          # once for the values, once for the field keys (not 4)
