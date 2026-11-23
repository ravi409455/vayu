"""PDF templates, report rendering, regeneration, verification."""
import io
import uuid

import pypdf
import pytest

from apps.bookings.models import Booking
from apps.bookings.tests.test_submissions import assign, publish_form, start
from apps.core import events
from apps.media import storage
from apps.media.tests.conftest import initiate_body, jpeg, put_parts
from apps.reports import context, definition
from apps.reports.models import PdfTemplateVersion, Report

from .conftest import create

pytestmark = pytest.mark.django_db
V = lambda k: {"var": k}  # noqa: E731
CHOICES = [{"key": "ok", "label": "Ok"},
           {"key": "dent", "label": "Dent", "is_defect": True, "severity": "major"}]
DEFN = {
    "filename": "{booking_id}{type_code}.pdf", "type_code": "PDI",
    "branding": {"title": "PRE DELIVERY CAR INSPECTION REPORT", "color": "#a62830",
                 "watermark": True},
    "blocks": [
        {"type": "cover", "photo": "photo_a", "rows": [
            {"label": "Booking ID", "field": "booking.booking_id"},
            {"label": "Chassis Number", "field": "chassis_no"},
            {"label": "Car", "field": "booking.car_make_model"}]},
        {"type": "ratings"},
        {"type": "table", "title": "Exterior Body", "rows": [
            {"label": "Driver Front Door", "field": "door"},
            {"label": "Odometer Reading", "field": "odometer"},
            {"label": "Key Check", "field": "dents"}]},
        {"type": "table", "title": "Dent Details", "show_if": {"==": [V("inspection.door"), "dent"]},
         "rows": [{"label": "Door", "field": "door"}]},
        {"type": "page_break"},
        {"type": "photos", "title": "Car Pictures", "columns": 2, "items": [
            {"field": "photo_a", "index": 0, "caption": "Front View"},
            {"field": "photo_a", "index": 1, "caption": "Rear View"}]},
        {"type": "text", "text": "Please refer to the last page for terms."},
    ]}


@pytest.fixture
def renv(env):
    admin = env.admin
    form = admin.post("/api/v1/forms", {"key": "pdi", "kind": "inspection", "name": "PDI",
                                        "inspection_type": "pdi"}, format="json").json()
    v = form["draft_version"]["id"]
    sec = admin.get(f"/api/v1/form-versions/{v}").json()["pages"][0]["sections"][0]["id"]

    def add(key, type_, **kw):
        cfg = kw.pop("config", {})
        r = admin.post(f"/api/v1/sections/{sec}/fields", {"key": key, "label": key, "type": type_,
                                                          "config": cfg, **kw}, format="json")
        assert r.status_code == 201, r.json()

    add("door", "single_choice", config={"options": CHOICES}, required=True)
    add("odometer", "number", config={"unit": "km"})
    add("photo_a", "photo", config={"max_count": 2})
    add("engine_rating", "rating", config={"category": "engine"})
    add("dents", "derived", config={"rule": {"some": [V("_defects"), {"in": [
        V(""), ["inspection.door"]]}]}, "true_label": "Found", "false_label": "Not Found"})
    admin.patch(f"/api/v1/form-versions/{v}/rating-config", {"config": {"categories": [
        {"key": "engine", "label": "Engine", "sections": ["Section 1"]}]}}, format="json")
    publish_form(admin, form["id"])
    t = admin.post("/api/v1/pdf-templates", {"form": form["id"]}, format="json").json()
    env.form_id, env.template_id = form["id"], t["id"]
    env.template_version_id = t["versions"][0]["id"]
    return env


def set_template(env, defn=DEFN, publish=True):
    v = env.admin.get(f"/api/v1/pdf-template-versions/{env.template_version_id}").json()
    r = env.admin.patch(f"/api/v1/pdf-template-versions/{v['id']}",
                        {"definition": defn, "row_version": v["row_version"]}, format="json")
    assert r.status_code == 200, r.json()
    if publish:
        p = env.admin.post(f"/api/v1/pdf-template-versions/{v['id']}/publish",
                           {"row_version": r.json()["row_version"]}, format="json")
        assert p.status_code == 200, p.json()


def photo(env, b, settings, color=(200, 30, 30)):
    data = jpeg(color=color)
    init = env.expert.post("/api/v1/media/initiate", initiate_body(b["id"], data, field_key="photo_a"),
                           format="json").json()
    parts = put_parts(init, data, settings)
    env.expert.post(f"/api/v1/media/{init['id']}/complete", {"parts": parts}, format="json")
    return init["id"]


def complete_job(env, booking_id="SA37926", door="dent", photos=2, settings=None):
    b = create(env.ops, booking_id=booking_id).json() if booking_id != "SA37926" else None
    if b is None:
        b = Booking.objects.filter(booking_id=booking_id).first()
        b = {"id": str(b.id)} if b else create(env.ops).json()
    assign(env, b)
    start(env.expert, b)
    ids = [photo(env, b, settings, (i * 40, 20, 20)) for i in range(photos)]
    body = {"client_submission_uuid": str(uuid.uuid4()), "answers": {"inspection": {
        "chassis_no": "MA3YPKCSKTJ273129", "door": door, "odometer": 45, "photo_a": ids}}}
    r = env.expert.post(f"/api/v1/bookings/{b['id']}/submit", body, format="json")
    assert r.status_code == 200, r.json()
    return b


def pdf_text(booking_id) -> tuple[str, pypdf.PdfReader]:
    report = Report.objects.get(booking_id=booking_id)
    reader = pypdf.PdfReader(io.BytesIO(storage.read(report.key)))
    return "\n".join(p.extract_text() for p in reader.pages), reader


# ---------------------------------------------------------------- definition validation

@pytest.mark.parametrize("bad", [
    [], {"surprise": 1}, {"filename": "x.txt"}, {"filename": "{nope}.pdf"},
    {"filename": "a/b.pdf"}, {"branding": {"color": "red"}}, {"branding": {"watermark": "yes"}},
    {"branding": {"x": 1}}, {"blocks": "x"}, {"blocks": [{"type": "video"}]},
    {"blocks": [{"type": "table", "rows": [{"label": "", "field": "a"}]}]},
    {"blocks": [{"type": "table", "rows": [{"label": "L"}]}]},
    {"blocks": [{"type": "table", "bogus": 1}]}, {"blocks": [{"type": "table", "font_size": "huge"}]},
    {"blocks": [{"type": "table", "show_if": {"missing": ["a"]}}]},
    {"blocks": [{"type": "photos", "columns": 5}]},
    {"blocks": [{"type": "photos", "items": [{"caption": "x"}]}]},
    {"blocks": [{"type": "spacer", "height": 0}]}, {"blocks": [{"type": "cover", "photo": 5}]},
    {"blocks": [{"type": "text", "text": 5}]},
    {"blocks": [{"type": "table", "rows": "nope"}]}, {"type_code": 5},
])
def test_bad_definitions_are_rejected(bad):
    with pytest.raises(ValueError):
        definition.validate_definition(bad)


def test_good_definitions_and_filenames():
    definition.validate_definition(DEFN)
    definition.validate_definition({})
    assert definition.filename_for(DEFN, "SA 37926", "14-10-2026") == "SA_37926PDI.pdf"
    assert definition.filename_for({"filename": "{date}-{booking_id}.pdf"}, "X1",
                                   "14-10-2026") == "14-10-2026-X1.pdf"
    assert definition.referenced_fields(DEFN) >= {("booking", "booking_id"), ("inspection", "door"),
                                                  ("inspection", "photo_a")}


# ---------------------------------------------------------------- template workflow API

def test_template_workflow(renv):
    a = renv.admin
    assert a.get("/api/v1/pdf-templates").json()[0]["form_key"] == "pdi"
    dup = a.post("/api/v1/pdf-templates", {"form": renv.form_id}, format="json")
    assert dup.status_code == 409 and dup.json()["code"] == "TEMPLATE_EXISTS"
    booking_form = a.get("/api/v1/forms").json()["results"]
    bf = [f for f in booking_form if f["kind"] == "booking"][0]
    assert a.post("/api/v1/pdf-templates", {"form": bf["id"]}, format="json").status_code == 400
    set_template(renv)
    v = a.get(f"/api/v1/pdf-template-versions/{renv.template_version_id}").json()
    assert v["status"] == "published" and v["definition"]["type_code"] == "PDI"
    pub_edit = a.patch(f"/api/v1/pdf-template-versions/{v['id']}", {"definition": DEFN,
                       "row_version": v["row_version"]}, format="json")
    assert pub_edit.status_code == 409 and pub_edit.json()["code"] == "VERSION_PUBLISHED"
    d = a.post(f"/api/v1/pdf-templates/{renv.template_id}/drafts")
    assert d.status_code == 201 and d.json()["number"] == 2 and d.json()["definition"] == DEFN
    again = a.post(f"/api/v1/pdf-templates/{renv.template_id}/drafts")
    assert again.status_code == 409 and again.json()["code"] == "DRAFT_EXISTS"


def test_template_edit_validation_and_stale_guard_and_audit(renv):
    from apps.accounts.models import AuditLog

    a = renv.admin
    v = a.get(f"/api/v1/pdf-template-versions/{renv.template_version_id}").json()
    url = f"/api/v1/pdf-template-versions/{v['id']}"
    bad = a.patch(url, {"definition": {"blocks": [{"type": "x"}]}, "row_version": 0}, format="json")
    assert bad.status_code == 400 and bad.json()["code"] == "INVALID_TEMPLATE"
    assert a.patch(url, {"definition": {}}, format="json").status_code == 400
    ok = a.patch(url, {"definition": DEFN, "row_version": 0}, format="json")
    stale = a.patch(url, {"definition": DEFN, "row_version": 0}, format="json")
    assert ok.status_code == 200 and stale.status_code == 409 and stale.json()["code"] == "STALE_DRAFT"
    a.post(f"{url}/publish", {"row_version": ok.json()["row_version"]}, format="json")
    assert AuditLog.objects.filter(action="pdf_template.publish").exists()
    assert a.post(f"{url}/publish", {"row_version": 9}, format="json").status_code == 409
    assert a.post(f"{url}/publish", {}, format="json").status_code == 400


def test_publish_is_blocked_by_unknown_fields(renv):
    a = renv.admin
    v = a.get(f"/api/v1/pdf-template-versions/{renv.template_version_id}").json()
    bad = {"blocks": [{"type": "table", "rows": [{"label": "X", "field": "ghost"},
                                                  {"label": "Y", "field": "booking.nope"}]}]}
    r = a.patch(f"/api/v1/pdf-template-versions/{v['id']}", {"definition": bad, "row_version": 0},
                format="json")
    p = a.post(f"/api/v1/pdf-template-versions/{v['id']}/publish",
               {"row_version": r.json()["row_version"]}, format="json")
    assert p.status_code == 400 and p.json()["code"] == "PUBLISH_BLOCKED"
    assert {i["message"] for i in p.json()["issues"]} == {
        "'inspection.ghost' is not a field of the inspection form.",
        "'booking.nope' is not a field of the booking form."}


def test_only_template_editors_can_change_templates(renv):
    from apps.accounts.catalog import DEFAULTS

    assert renv.ops.get("/api/v1/pdf-templates").status_code == 403       # no pdf_templates.view
    perms = {**DEFAULTS["ops"], "pdf_templates.view": "all"}
    renv.admin.put("/api/v1/roles/ops/permissions", {"permissions": perms}, format="json")
    assert renv.ops.get("/api/v1/pdf-templates").status_code == 200
    assert renv.ops.post("/api/v1/pdf-templates", {"form": renv.form_id},
                         format="json").status_code == 403
    assert renv.ops.post(f"/api/v1/pdf-templates/{renv.template_id}/drafts").status_code == 403


def test_form_publish_warns_about_fields_the_template_never_shows(renv):
    set_template(renv, {"blocks": [{"type": "table", "rows": [
        {"label": "Door", "field": "door"}]}]})
    d = renv.admin.post(f"/api/v1/forms/{renv.form_id}/drafts").json()["id"]
    rv = renv.admin.get(f"/api/v1/form-versions/{d}").json()["row_version"]
    r = renv.admin.post(f"/api/v1/form-versions/{d}/publish", {"row_version": rv}, format="json")
    assert r.status_code == 200
    keys = {w["key"] for w in r.json()["warnings"]}
    assert "odometer" in keys and "door" not in keys
    assert {w["code"] for w in r.json()["warnings"]} == {"FIELD_NOT_IN_PDF"}


def test_publish_has_no_warnings_without_a_template(env):
    f = env.admin.post("/api/v1/forms", {"key": "ppi", "kind": "inspection", "name": "PPI"},
                       format="json").json()
    rv = env.admin.get(f"/api/v1/form-versions/{f['draft_version']['id']}").json()["row_version"]
    r = env.admin.post(f"/api/v1/form-versions/{f['draft_version']['id']}/publish",
                       {"row_version": rv}, format="json")
    assert r.json()["warnings"] == []


# ---------------------------------------------------------------- context

def test_missing_and_hidden_things_never_break_the_report(renv, settings):
    set_template(renv)
    b = complete_job(renv, door="ok", photos=1, settings=settings)
    booking = Booking.objects.get(pk=b["id"])
    insp = context.latest_inspection(booking)
    assert insp is not None
    unknown = {"blocks": [{"type": "table", "title": "T", "rows": [
        {"label": "Old field", "field": "no_such_field"}, {"label": "Door", "field": "door"}]},
        {"type": "photos", "items": [{"field": "photo_a", "index": 5, "caption": "none"}]}]}
    blocks = context.build(booking, insp, unknown)
    rows = {r["label"]: r for r in blocks[0]["rows"]}
    assert rows["Old field"]["text"] == "" and rows["Door"]["text"] == "Ok"
    assert blocks[1]["items"][0]["media"] is None
    shown = context.build(booking, insp, DEFN)
    assert "Dent Details" not in [b.get("title") for b in shown]      # show_if false: dropped


def test_values_are_formatted_and_defects_flagged(renv, settings):
    set_template(renv)
    b = complete_job(renv, door="dent", photos=1, settings=settings)
    booking = Booking.objects.get(pk=b["id"])
    insp = context.latest_inspection(booking)
    assert insp is not None
    blocks = context.build(booking, insp, DEFN)
    by_title = {b.get("title"): b for b in blocks}
    ext = {r["label"]: r for r in by_title["Exterior Body"]["rows"]}
    assert ext["Driver Front Door"] == {"label": "Driver Front Door", "text": "Dent", "defect": True}
    assert ext["Odometer Reading"]["text"] == "45 km" and ext["Key Check"]["text"] == "Found"
    assert "Dent Details" in by_title                                  # show_if true
    cover = blocks[0]
    assert cover["photo"] and {r["label"] for r in cover["rows"]} == {
        "Booking ID", "Chassis Number", "Car"}
    assert [r for r in cover["rows"] if r["label"] == "Car"][0]["text"] == "Maruti Victoris"
    ratings = [b for b in blocks if b["type"] == "ratings"][0]
    assert ratings["rows"] == [{"label": "Engine", "text": "4/5", "defect": False}]
    assert ratings["overall"] == "Good"


def test_display_formats_every_field_type():
    from apps.forms.models import Field
    from apps.reports.context import display

    def f(t, **c):
        return Field(key="k", type=t, config=c)

    assert display(f("yes_no"), True, {}) == ("Yes", False)
    assert display(f("multi_choice", options=CHOICES), ["ok", "dent"], {}) == ("Ok, Dent", True)
    assert display(f("currency"), 1500, {}) == ("₹1,500", False)
    assert display(f("currency"), 1499.5, {})[0] == "₹1,499.50"
    assert display(f("date"), "2026-10-14", {}) == ("14-10-2026", False)
    assert display(f("datetime"), "2026-10-14T15:29:00+05:30", {})[0] == "14-10-2026 15:29"
    assert display(f("gps"), {"lat": 28.6, "lng": 77.2}, {})[0] == "28.60000, 77.20000"
    assert display(f("photo"), ["a", "b"], {}) == ("2 photos", False)
    assert display(f("video"), ["a"], {}) == ("1 video", False)
    assert display(f("signature"), "x", {}) == ("Signed", False)
    assert display(f("rating"), 4, {}) == ("4/5", False)
    assert display(f("short_text"), "hello", {}) == ("hello", False)
    assert display(f("number"), 7, {}) == ("7", False)
    assert display(None, "x", {}) == ("", False) and display(f("short_text"), None, {}) == ("", False)
    assert display(f("derived", true_label="Found", false_label="No"), False, {}) == ("No", False)


# ---------------------------------------------------------------- rendering end to end

def test_a_completed_booking_gets_a_pdf_automatically(renv, settings):
    set_template(renv)
    b = complete_job(renv, settings=settings)
    r = Report.objects.get(booking_id=b["id"])
    assert r.status == "ready" and r.revision == 1 and r.filename == "SA37926PDI.pdf"
    assert len(r.token) >= 32 and storage.exists(r.key) and r.template_version_id
    text, reader = pdf_text(b["id"])
    for needle in ("PRE DELIVERY CAR INSPECTION REPORT", "Booking ID", "SA37926", "Chassis Number",
                   "MA3YPKCSKTJ273129", "Driver Front Door", "Dent", "45 km", "Overall Rating",
                   "Front View", "Rear View", "Please refer to the last page"):
        assert needle in text, needle
    assert "Page 1 of 2" in text and "Page 2 of 2" in text and "rev 1" in text
    assert "Generated" in text and f"verify.carcid.in/{r.token}" in text
    assert len(reader.pages) == 2                                    # the page break
    assert sum(len(p.images) for p in reader.pages) >= 3             # hero + 2 grid photos + QR
    assert "gallery" not in text.lower() and "camera" not in text.lower()


def test_no_template_means_no_report_but_the_booking_still_completes(env, settings):
    f = env.admin.post("/api/v1/forms", {"key": "pdi", "kind": "inspection", "name": "PDI",
                                         "inspection_type": "pdi"}, format="json").json()
    publish_form(env.admin, f["id"])
    b = create(env.ops, booking_id="NT1").json()
    assign(env, b)
    start(env.expert, b)
    body = {"client_submission_uuid": str(uuid.uuid4()),
            "answers": {"inspection": {"chassis_no": "MA3YPKCSKTJ273129"}}}
    assert env.expert.post(f"/api/v1/bookings/{b['id']}/submit", body, format="json"
                           ).status_code == 200
    assert Booking.objects.get(pk=b["id"]).stage == "completed"
    assert not Report.objects.exists()
    assert env.ops.get(f"/api/v1/bookings/{b['id']}/report").status_code == 404


def test_regenerate_after_an_edit_keeps_one_pdf_and_the_same_token(renv, settings):
    set_template(renv)
    b = complete_job(renv, settings=settings)
    first = Report.objects.get(booking_id=b["id"])
    old_key, token = first.key, first.token
    from apps.bookings.models import Inspection

    insp = Inspection.objects.get(booking_id=b["id"])
    r = renv.ops.patch(f"/api/v1/inspections/{insp.id}", {
        "answers": {"inspection": {"odometer": 99}}, "row_version": 0}, format="json")
    assert r.status_code == 200
    stale = renv.ops.get(f"/api/v1/bookings/{b['id']}/report").json()
    assert stale["stale"] is True and stale["revision"] == 1           # not regenerated yet
    assert renv.ops.get("/api/v1/problems/reports").json()[0]["stale"] is True
    g = renv.ops.post(f"/api/v1/bookings/{b['id']}/report/regenerate")
    assert g.status_code == 202
    now = Report.objects.get(booking_id=b["id"])
    assert now.revision == 2 and now.stale is False and now.token == token
    assert not storage.exists(old_key) and storage.exists(now.key)    # only the latest is kept
    text, _ = pdf_text(b["id"])
    assert "99 km" in text and "rev 2" in text
    assert renv.ops.get("/api/v1/problems/reports").json() == []
    url = renv.ops.get(f"/api/v1/bookings/{b['id']}/report").json()
    assert url["url"].startswith("https://") and url["filename"] == "SA37926PDI.pdf"


def test_regenerate_needs_permission_and_a_completed_booking(renv, settings):
    set_template(renv)
    b = create(renv.ops, booking_id="RG1").json()
    assert renv.ops.post(f"/api/v1/bookings/{b['id']}/report/regenerate").status_code == 409
    assert renv.expert.post(f"/api/v1/bookings/{b['id']}/report/regenerate").status_code == 403


def test_a_failing_render_is_retried_then_recorded_and_alerted(renv, settings, monkeypatch):
    from apps.reports import render

    set_template(renv)
    calls = []

    def boom(html):
        calls.append(1)
        raise RuntimeError("renderer crashed")

    monkeypatch.setattr(render, "render_pdf", boom)
    with events.capture() as seen:
        b = complete_job(renv, settings=settings)
    r = Report.objects.get(booking_id=b["id"])
    assert r.status == "failed" and r.error == "render_failed" and len(calls) == 3   # 1 + 2 retries
    assert "renderer crashed" not in r.error                      # raw error text stays in the logs
    assert "alert.pdf_failed" in [n for n, _ in seen]
    assert renv.ops.get("/api/v1/problems/reports").json()[0]["status"] == "failed"
    monkeypatch.undo()
    renv.ops.post(f"/api/v1/bookings/{b['id']}/report/regenerate")
    assert Report.objects.get(booking_id=b["id"]).status == "ready"


def test_pdf_renders_run_on_a_one_at_a_time_queue():
    from pathlib import Path

    from django.conf import settings as s

    assert s.CELERY_TASK_ROUTES["apps.reports.tasks.render_report"] == {"queue": "pdf"}
    compose = (Path(__file__).resolve().parents[4] / "infra" / "docker-compose.prod.yml").read_text()
    assert "-Q pdf -c 1" in compose


def test_preview_renders_a_template_with_real_data_without_storing_anything(renv, settings):
    set_template(renv)
    b = complete_job(renv, settings=settings)
    before = Report.objects.get(booking_id=b["id"]).revision
    draft = renv.admin.post(f"/api/v1/pdf-templates/{renv.template_id}/drafts").json()
    r = renv.admin.post(f"/api/v1/pdf-template-versions/{draft['id']}/preview",
                        {"booking": b["id"]}, format="json")
    assert r.status_code == 200 and r["Content-Type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-"
    assert Report.objects.get(booking_id=b["id"]).revision == before
    other = create(renv.ops, booking_id="PV2").json()
    bad = renv.admin.post(f"/api/v1/pdf-template-versions/{draft['id']}/preview",
                          {"booking": other["id"]}, format="json")
    assert bad.status_code == 400 and bad.json()["code"] == "INVALID_BOOKING"


# ---------------------------------------------------------------- verify page

def test_verify_shows_a_summary_and_nothing_about_the_customer(renv, settings):
    from rest_framework.test import APIClient

    set_template(renv)
    b = complete_job(renv, settings=settings)
    token = Report.objects.get(booking_id=b["id"]).token
    r = APIClient().get(f"/api/v1/verify/{token}")
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is True and body["booking_id"] == "SA37926"
    assert body["car"] == "Maruti Victoris" and body["type"] == "PDI (new car)"
    assert body["overall_rating"] == "good" and body["revision"] == 1 and body["current"] is True
    blob = str(body)
    for private in ("Asha", "9876543210", "MG Road", "delhi", "MA3YPKCSKTJ273129"):
        assert private not in blob


def test_verify_reports_when_a_newer_revision_is_pending_and_rejects_bad_tokens(renv, settings):
    from rest_framework.test import APIClient

    set_template(renv)
    b = complete_job(renv, settings=settings)
    Report.objects.filter(booking_id=b["id"]).update(stale=True)
    token = Report.objects.get(booking_id=b["id"]).token
    assert APIClient().get(f"/api/v1/verify/{token}").json()["current"] is False
    assert APIClient().get("/api/v1/verify/nope").status_code == 404
    Report.objects.filter(booking_id=b["id"]).update(status="failed")
    assert APIClient().get(f"/api/v1/verify/{token}").status_code == 404


def test_report_access_follows_the_reports_view_scope(renv, settings):
    set_template(renv)
    b = complete_job(renv, settings=settings)
    assert renv.expert.get(f"/api/v1/bookings/{b['id']}/report").status_code == 403   # no reports.view
    assert renv.ops.get(f"/api/v1/bookings/{b['id']}/report").status_code == 200
    renv.admin.put("/api/v1/roles/expert/permissions", {"permissions": {
        "reports.view": "own", "bookings.view": "own"}}, format="json")
    assert renv.expert.get(f"/api/v1/bookings/{b['id']}/report").status_code == 200   # their own job
    other = create(renv.ops, booking_id="OT1").json()
    assert renv.expert.get(f"/api/v1/bookings/{other['id']}/report").status_code == 404
    assert renv.expert.get("/api/v1/problems/reports").status_code == 200
    assert PdfTemplateVersion.objects.count() == 1


def test_rating_fields_user_pickers_headings_and_spacers_render(renv, settings, db):
    from apps.accounts.models import User
    from apps.forms.models import Field
    from apps.reports.context import display
    from apps.reports.render import render_html

    set_template(renv)
    b = complete_job(renv, settings=settings)
    booking = Booking.objects.get(pk=b["id"])
    insp = context.latest_inspection(booking)
    assert insp is not None
    blocks = context.build(booking, insp, {"blocks": [{"type": "table", "title": "T", "rows": [
        {"label": "Rating", "field": "engine_rating"}]}]})
    assert blocks[0]["rows"][0]["text"] == "4/5"
    user = User.objects.get(pk=renv.expert_user.pk)
    assert display(Field(key="k", type="user_picker", config={}), user.pk, {})[0] == (
        user.name or user.username)
    assert display(Field(key="k", type="user_picker", config={}), 999999, {})[0] == ""
    html_text = render_html(
        [{"type": "heading", "text": "Big <b>", "font_size": "large"},
         {"type": "spacer", "height": 30, "font_size": "medium"},
         {"type": "page_break", "font_size": "medium"}],
        {"branding": {}}, booking_id="X1", revision=3, stamp="now", token="tok")
    assert "Big &lt;b&gt;" in html_text and "height:30px" in html_text and "rev 3" in html_text


def test_publishing_a_template_works_without_a_booking_form_and_detects_stale_drafts(db, api_as):
    from apps.accounts.models import Role

    admin, _ = api_as(Role.ADMIN)
    form = admin.post("/api/v1/forms", {"key": "pdi", "kind": "inspection", "name": "PDI"},
                      format="json").json()
    t = admin.post("/api/v1/pdf-templates", {"form": form["id"]}, format="json").json()
    v = t["versions"][0]["id"]
    ok = admin.post(f"/api/v1/pdf-template-versions/{v}/publish", {"row_version": 0}, format="json")
    assert ok.status_code == 200
    d = admin.post(f"/api/v1/pdf-templates/{t['id']}/drafts").json()
    stale = admin.post(f"/api/v1/pdf-template-versions/{d['id']}/publish", {"row_version": 5},
                       format="json")
    assert stale.status_code == 409 and stale.json()["code"] == "STALE_DRAFT"


def test_a_storage_failure_is_recorded_as_such_and_previews_need_reports_view(renv, settings,
                                                                               monkeypatch):
    from botocore.exceptions import ClientError

    from apps.accounts.catalog import DEFAULTS
    from apps.media import storage as st

    set_template(renv)
    real_put = st.put

    def failing_put(key, data, content_type):
        if key.startswith("reports/"):
            raise ClientError({"Error": {"Code": "500", "Message": "https://secret.example"}}, "Put")
        return real_put(key, data, content_type)

    monkeypatch.setattr(st, "put", failing_put)
    b = complete_job(renv, settings=settings)
    r = Report.objects.get(booking_id=b["id"])
    assert r.error == "storage_failed" and "secret" not in r.error
    monkeypatch.undo()
    draft = renv.admin.post(f"/api/v1/pdf-templates/{renv.template_id}/drafts").json()
    perms = {**DEFAULTS["ops"], "pdf_templates.edit": "all", "pdf_templates.view": "all"}
    perms.pop("reports.view")
    renv.admin.put("/api/v1/roles/ops/permissions", {"permissions": perms}, format="json")
    r = renv.ops.post(f"/api/v1/pdf-template-versions/{draft['id']}/preview",
                      {"booking": b["id"]}, format="json")
    assert r.status_code == 403 and r.json()["code"] == "FORBIDDEN"


@pytest.mark.real_commit
def test_the_pdf_job_waits_for_the_commit(renv, settings, django_capture_on_commit_callbacks):
    """submit() emits 'completed' inside its transaction; a worker must not start before it is saved."""
    from unittest import mock

    set_template(renv)
    with mock.patch("apps.reports.tasks.render_report.delay") as queued:
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            complete_job(renv, settings=settings)
        queued.assert_not_called()           # nothing queued while the transaction is open
        assert callbacks
        for cb in callbacks:
            cb()
        queued.assert_called_once()
