"""PDF templates (schema 2), report rendering, regeneration, verification."""
import copy
import io
import uuid

import pypdf
import pytest

from apps.bookings.models import Booking
from apps.bookings.tests.conftest import custom_form
from apps.bookings.tests.test_submissions import assign, publish_form, start
from apps.core import events
from apps.media import storage
from apps.media.tests.conftest import initiate_body, jpeg, put_parts
from apps.reports import context, definition, placeholders, render
from apps.reports.models import PdfTemplateVersion, Report

from .conftest import create

pytestmark = pytest.mark.django_db
V = lambda k: {"var": k}  # noqa: E731
CHOICES = [{"key": "ok", "label": "Ok", "tone": "ok"},
           {"key": "scratch", "label": "Scratch", "is_defect": True, "severity": "minor"},
           {"key": "dent", "label": "Dent", "is_defect": True, "severity": "major"},
           {"key": "na", "label": "Not available", "tone": "muted"},
           {"key": "not_checked", "label": "Not able to check", "tone": "warn"}]
DENT = {"==": [V("inspection.door"), "dent"]}
BAND = {"header": {"left": [{"text": "<strong>PRE DELIVERY CAR INSPECTION REPORT</strong>"}],
                   "right": [{"text": "{{ sys.booking_id }}"}], "background": "brand"},
        "footer": {"left": [{"text": "rev {{ sys.revision }}"}],
                   "right": [{"text": "Page {{ sys.page }} of {{ sys.pages }}"}]}}
DEFN = {
    "schema": 2, "filename": "{{ sys.booking_id }}PDI.pdf",
    "bands": {"cover": BAND, "normal": BAND},
    "pages": [
        {"title": "Cover", "style": "cover", "parts": [
            {"type": "photos", "which": "first", "per_row": 1, "caption": "none",
             "source": {"kind": "fields", "fields": ["inspection.photo_a"]}},
            {"type": "table", "title": "Vehicle", "source": {"kind": "fields", "rows": [
                {"field": "booking.booking_id", "label": "Booking ID"},
                {"field": "inspection.chassis_no", "label": "Chassis Number"},
                {"field": "booking.car_make_model", "label": "Car"}]}},
            {"type": "table", "title": "Overall Rating", "look": {"header": True},
             "source": {"kind": "grid", "columns": [{"label": "Engine"}, {"label": "Expert"}],
                        "rows": [{"label": "Rating", "cells": [
                            {"field": "inspection.engine_rating"},
                            {"text": "{{ sys.overall }}"}]}]}}]},
        {"title": "Detail", "parts": [
            {"type": "table", "title": "Exterior Body", "source": {"kind": "fields", "rows": [
                {"field": "inspection.door", "label": "Driver Front Door"},
                {"field": "inspection.odometer", "label": "Odometer Reading"},
                {"field": "inspection.dents", "label": "Key Check"}]}},
            {"type": "table", "title": "Dent Details", "show_if": DENT,
             "source": {"kind": "fields", "rows": [{"field": "inspection.door", "label": "Door"}]}},
            {"type": "photos", "title": "Car Pictures", "per_row": 2,
             "source": {"kind": "fields", "fields": ["inspection.photo_a"]}},
            {"type": "text", "html": "<p>Please refer to the last page for terms.</p>"},
            {"type": "verify"}]}]}


@pytest.fixture
def renv(env):
    admin = env.admin
    form = custom_form(admin, "pdi", "PDI")
    v = form["draft_version"]["id"]
    page = admin.get(f"/api/v1/form-versions/{v}").json()["pages"][0]
    sec = page["sections"][0]["id"]

    def add(key, type_, section=sec, **kw):
        cfg = kw.pop("config", {})
        r = admin.post(f"/api/v1/sections/{section}/fields", {"key": key, "label": key,
                                                              "type": type_, "config": cfg, **kw},
                       format="json")
        assert r.status_code == 201, r.json()

    add("door", "single_choice", config={"options": CHOICES}, required=True)
    add("door_photo", "photo", config={"max_count": 2, "photo_of": "door"}, show_if=DENT)
    add("odometer", "number", config={"unit": "km"})
    add("photo_a", "photo", config={"max_count": 2})
    add("engine_rating", "rating", config={"category": "engine"})
    add("dents", "derived", config={"rule": {"some": [V("_defects"), {"in": [
        V(""), ["inspection.door"]]}]}, "true_label": "Found", "false_label": "Not Found"})
    extra = admin.post(f"/api/v1/pages/{page['id']}/sections", {"title": "Extra"},
                       format="json").json()["id"]
    add("dent_note", "short_text", section=extra, show_if=DENT)
    add("fuel", "single_choice", section=extra,
        config={"options": [{"key": "petrol", "label": "Petrol"}]})
    add("issue_pics", "photo", section=extra, config={"max_count": 2, "issue_photo": True})
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


def photo(env, b, settings, color=(200, 30, 30), field="photo_a"):
    data = jpeg(color=color)
    init = env.expert.post("/api/v1/media/initiate", initiate_body(b["id"], data, field_key=field),
                           format="json").json()
    parts = put_parts(init, data, settings)
    env.expert.post(f"/api/v1/media/{init['id']}/complete", {"parts": parts}, format="json")
    return init["id"]


def complete_job(env, booking_id="SA37926", door="dent", photos=2, settings=None, **extra):
    b = create(env.ops, booking_id=booking_id).json() if booking_id != "SA37926" else None
    if b is None:
        b = Booking.objects.filter(booking_id=booking_id).first()
        b = {"id": str(b.id)} if b else create(env.ops).json()
    assign(env, b)
    start(env.expert, b)
    ids = [photo(env, b, settings, (i * 40, 20, 20)) for i in range(photos)]
    answers = {"chassis_no": "MA3YPKCSKTJ273129", "door": door, "odometer": 45, "photo_a": ids,
               **extra}
    if door == "dent":
        answers["door_photo"] = [photo(env, b, settings, field="door_photo")]
    body = {"client_submission_uuid": str(uuid.uuid4()), "answers": {"inspection": answers}}
    r = env.expert.post(f"/api/v1/bookings/{b['id']}/submit", body, format="json")
    assert r.status_code == 200, r.json()
    return b


def pdf_text(booking_id) -> tuple[str, pypdf.PdfReader]:
    report = Report.objects.get(booking_id=booking_id)
    reader = pypdf.PdfReader(io.BytesIO(storage.read(report.key)))
    return "\n".join(p.extract_text() for p in reader.pages), reader


def source(b, revision=1, token="tok"):
    booking = Booking.objects.get(pk=b["id"])
    insp = context.latest_inspection(booking)
    assert insp is not None
    return context.Source(booking, insp, revision=revision, token=token)


def one_page(*parts, style="normal"):
    return {"schema": 2, "pages": [{"title": "P", "style": style, "parts": list(parts)}]}


def table(rows=None, **kw):
    return {"type": "table", "source": {"kind": "fields", "rows": rows or []}, **kw}


# ---------------------------------------------------------------- definition validation

@pytest.mark.parametrize("bad", [
    [], {"surprise": 1}, {"schema": 1, "pages": []}, {"schema": 2},
    {"schema": 2, "pages": [], "filename": "x.txt"},
    {"schema": 2, "pages": [], "filename": "{{ nope }}.pdf"},
    {"schema": 2, "pages": [], "filename": "{% if 1 %}x{% endif %}.pdf"},
    {"schema": 2, "pages": [], "filename": "{{ sys.booking_id | upper }}.pdf"},
    {"schema": 2, "pages": [], "filename": "{{ sys.booking_id.pdf"},
    {"schema": 2, "pages": [], "theme": {"colors": {"brand": "red"}}},
    {"schema": 2, "pages": [{"title": "P", "parts": [{"type": "video"}]}]},
    one_page(table([{"field": "door"}])),                                # not form.key
    one_page(table(bogus=1)), one_page(table(show_if={"missing": ["a"]})),
    one_page({"type": "photos", "per_row": 5, "source": {"kind": "issues"}}),
    one_page({"type": "spacer", "height": 0}),
    one_page({"type": "text", "html": 5}),
    one_page({"type": "text", "html": "{{ booking.x() }}"}),
    one_page(table([{"field": "inspection.door", "show_if": {"a": 1, "b": 2}}])),
    {"schema": 2, "pages": [{"title": "P", "show_if": {"a": 1, "b": 2}, "parts": []}]},
    {"schema": 2, "pages": [{"id": "a", "title": "P", "parts": [{"type": "spacer", "id": "a"}]}]},
    {"schema": 2, "pages": [], "bands": {"normal": {"header": {"left": [{"text": "{{ x.y }}"}]}}}},
    one_page({"type": "table", "source": {"kind": "grid", "columns": [{"label": "A"}],
                                          "rows": [{"label": "{{ q }}", "cells": []}]}}),
    one_page({"type": "table", "source": {"kind": "grid", "columns": [{"label": "A"}],
                                          "rows": [{"label": "", "cells": [{"text": "{{ q }}"}]}]}}),
    one_page({"type": "photos", "caption": "custom", "caption_text": "{{ q }}",
              "source": {"kind": "issues"}}),
    one_page(table(style_rules=[{"when": "sometimes"}])),
    one_page({"type": "html", "html": '<p style="font-family:{{ inspection.colour }}">x</p>'}),
    one_page({"type": "html", "html": "<p>{{ inspection.x | upper }}</p>"}),
    *[one_page({"type": "html", "html": "<p>x</p>", "css": css}) for css in (
        "p { background: url(data:x) }", "@import 'x.css';", "p { color: \\72 ed }",
        "p { background: u\\rl(http://x) }", "p { background: image-set('http://x' 1x) }",
        "p { background: image(http://x) }",
        "p { } </style>", "p { color: red", "} body { color: red } p {")],
])
def test_bad_definitions_are_rejected(bad):
    with pytest.raises(ValueError):
        definition.validate_definition(bad)


def test_an_old_template_gets_a_clear_message():
    with pytest.raises(ValueError, match="old report designer"):
        definition.validate_definition({"blocks": []})


def test_good_definitions_and_filenames():
    d = copy.deepcopy(DEFN)
    assert definition.validate_definition(d) == d
    assert definition.filename_for(DEFN, {"sys": {"booking_id": "SA 37926"}}) == "SA_37926PDI.pdf"
    assert definition.filename_for({}, {"sys": {"booking_id": "X1"}}) == "X1.pdf"
    assert definition.filename_for({"filename": "{{ inspection.colour }}.pdf"},
                                   {"inspection": {"colour": ""}}) == ".pdf"
    assert definition.referenced_fields(DEFN) >= {("booking", "booking_id"), ("inspection", "door"),
                                                  ("inspection", "photo_a")}


def test_rich_text_and_band_text_are_cleaned_and_placeholders_found():
    d = one_page({"type": "text", "html": '<p class="tone-bad evil">Hi {{ inspection.colour }}'
                                          '<script>x()</script><img src="http://x/y.png">'
                                          '<a href="javascript:alert(1)">l</a></p>'})
    d["bands"] = {"normal": {"header": {"left": [{"text": "<b>A</b><iframe src=x></iframe>"}]}}}
    out = definition.validate_definition(d)
    html = out["pages"][0]["parts"][0]["html"]
    assert "script" not in html and "img" not in html and "javascript" not in html
    assert 'class="tone-bad"' in html and "{{ inspection.colour }}" in html
    assert out["bands"]["normal"]["header"]["left"][0]["text"] == "<b>A</b>"
    assert ("inspection", "colour") in definition.referenced_fields(out)
    assert placeholders.refs("{{ sys.booking_id }} {{ booking.city }}") == {("booking", "city")}


def test_placeholder_values_are_escaped():
    assert placeholders.render("{{ inspection.x }}", {"inspection": {"x": "<b>"}}) == "&lt;b&gt;"
    assert placeholders.render("{{ inspection.missing.deep }}", {"inspection": {}}) == ""
    assert placeholders.render("{{ inspection.x }}", {"inspection": {"x": "<b>"}},
                               html=False) == "<b>"


def test_sections_and_exclusions_count_as_used():
    d = one_page({"type": "table", "source": {"kind": "section", "section": "inspection.extra",
                                              "exclude": ["fuel"]}},
                 {"type": "photos", "source": {"kind": "section", "section": "inspection.x"}})
    assert definition.referenced_sections(d) == {"extra", "x"}
    assert ("inspection", "fuel") in definition.referenced_fields(d)


# ---------------------------------------------------------------- template workflow API

def test_template_workflow(renv):
    a = renv.admin
    assert a.get("/api/v1/pdf-templates").json()[0]["form_key"] == "pdi"
    dup = a.post("/api/v1/pdf-templates", {"form": renv.form_id}, format="json")
    assert dup.status_code == 409 and dup.json()["code"] == "TEMPLATE_EXISTS"
    forms = a.get("/api/v1/forms").json()["results"]
    bf = [f for f in forms if f["type"] == "booking"][0]
    assert a.post("/api/v1/pdf-templates", {"form": bf["id"]}, format="json").status_code == 400
    set_template(renv)
    v = a.get(f"/api/v1/pdf-template-versions/{renv.template_version_id}").json()
    assert v["status"] == "published" and v["definition"]["schema"] == 2
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
    bad = a.patch(url, {"definition": {"schema": 2, "pages": "x"}, "row_version": 0},
                  format="json")
    assert bad.status_code == 400 and bad.json()["code"] == "INVALID_TEMPLATE"
    assert "pages" in bad.json()["detail"]
    assert a.patch(url, {"definition": {}}, format="json").status_code == 400
    ok = a.patch(url, {"definition": DEFN, "row_version": 0}, format="json")
    stale = a.patch(url, {"definition": DEFN, "row_version": 0}, format="json")
    assert ok.status_code == 200 and stale.status_code == 409 and stale.json()["code"] == "STALE_DRAFT"
    a.post(f"{url}/publish", {"row_version": ok.json()["row_version"]}, format="json")
    assert AuditLog.objects.filter(action="pdf_template.publish").exists()
    assert a.post(f"{url}/publish", {"row_version": 9}, format="json").status_code == 409
    assert a.post(f"{url}/publish", {}, format="json").status_code == 400


def test_publish_is_blocked_by_unknown_fields_and_sections(renv):
    a = renv.admin
    v = a.get(f"/api/v1/pdf-template-versions/{renv.template_version_id}").json()
    bad = one_page(table([{"field": "inspection.ghost"}, {"field": "booking.nope"}]),
                   {"type": "table", "source": {"kind": "section",
                                                "section": "inspection.nowhere"}})
    r = a.patch(f"/api/v1/pdf-template-versions/{v['id']}", {"definition": bad, "row_version": 0},
                format="json")
    p = a.post(f"/api/v1/pdf-template-versions/{v['id']}/publish",
               {"row_version": r.json()["row_version"]}, format="json")
    assert p.status_code == 400 and p.json()["code"] == "PUBLISH_BLOCKED"
    assert {i["message"] for i in p.json()["issues"]} == {
        "'inspection.ghost' is not a field of the inspection form.",
        "'booking.nope' is not a field of the booking form.",
        "Section 'nowhere' is not a section of the form."}


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
    set_template(renv, one_page(table([{"field": "inspection.door"}]),
                                {"type": "table", "source": {"kind": "section",
                                                             "section": "inspection.extra"}}))
    d = renv.admin.post(f"/api/v1/forms/{renv.form_id}/drafts").json()["id"]
    rv = renv.admin.get(f"/api/v1/form-versions/{d}").json()["row_version"]
    r = renv.admin.post(f"/api/v1/form-versions/{d}/publish", {"row_version": rv}, format="json")
    assert r.status_code == 200
    keys = {w["key"] for w in r.json()["warnings"]}
    assert "odometer" in keys and "door" not in keys
    assert "fuel" not in keys and "dent_note" not in keys           # the whole section is shown
    assert {w["code"] for w in r.json()["warnings"]} == {"FIELD_NOT_IN_PDF"}


def test_publish_has_no_warnings_without_a_template(env):
    f = env.admin.post("/api/v1/forms", {"key": "ppi", "name": "PPI"},
                       format="json").json()
    rv = env.admin.get(f"/api/v1/form-versions/{f['draft_version']['id']}").json()["row_version"]
    r = env.admin.post(f"/api/v1/form-versions/{f['draft_version']['id']}/publish",
                       {"row_version": rv}, format="json")
    assert r.json()["warnings"] == []


# ---------------------------------------------------------------- working out the content

def test_rows_hide_when_empty_or_hidden_and_keep_their_fallback(renv, settings):
    b = complete_job(renv, door="ok", photos=1, settings=settings)
    src = source(b)
    d = one_page(
        table([{"field": "inspection.ghost"}, {"field": "inspection.door", "label": "Door"},
               {"field": "inspection.fuel", "fallback": "Not mentioned"},
               {"field": "inspection.dent_note", "fallback": "never"},          # hidden: no row
               {"field": "inspection.odometer", "show_if": DENT}], title="T"),
        table([{"field": "inspection.fuel"}], title="Empty"),                     # dropped
        {**table([{"field": "inspection.fuel"}], title="Kept"), "hide_when_empty": False},
        {"type": "photos", "source": {"kind": "fields", "fields": ["inspection.ghost",
                                                                   "inspection.door_photo"]}},
        {"type": "text", "html": "   "},
        {"type": "spacer"}, {"type": "page_break"})
    d["pages"].append({"title": "Gone", "show_if": DENT, "parts": [{"type": "spacer"}]})
    d["pages"].append({"title": "Empty", "parts": [table([{"field": "inspection.fuel"}])]})
    pages = context.build(src, d)
    assert len(pages) == 1
    parts = pages[0]["parts"]
    assert [p["type"] for p in parts] == ["table", "table", "spacer", "page_break"]
    rows = {r["label"]: r for r in parts[0]["rows"]}
    assert set(rows) == {"Door", "fuel"}
    assert rows["Door"]["text"] == "Ok" and rows["Door"]["tone"] == "ok"
    assert rows["fuel"] == {"label": "fuel", "text": "Not mentioned", "tone": None,
                            "problem": False, "empty": True, "flags": ["empty"]}
    assert parts[1]["rows"] == []


def test_values_tones_and_problems(renv, settings):
    b = complete_job(renv, door="dent", photos=1, settings=settings, fuel="petrol")
    src = source(b)
    by = {p.get("title"): p for p in context.build(src, DEFN)[1]["parts"]}
    ext = {r["label"]: r for r in by["Exterior Body"]["rows"]}
    assert ext["Driver Front Door"] == {"label": "Driver Front Door", "text": "Dent", "tone": "bad",
                                        "problem": True, "empty": False,
                                        "flags": ["problem", "bad", "major"]}
    assert ext["Odometer Reading"]["text"] == "45 km" and ext["Key Check"]["text"] == "Found"
    assert ext["Key Check"]["tone"] == "bad"
    assert "Dent Details" in by                                      # show_if true
    cover = context.build(src, DEFN)[0]["parts"]
    assert len(cover[0]["items"]) == 1                               # which: first
    vehicle = {r["label"]: r["text"] for r in cover[1]["rows"]}
    assert vehicle["Car"] == "Maruti Victoris"
    grid = cover[2]["rows"][0]
    assert grid["label"] == "Rating" and [c["text"] for c in grid["cells"]] == ["4/5", "Good"]
    fuel = src.cell("inspection.fuel")
    assert fuel.text == "Petrol" and fuel.tone is None               # a fact, not a check


def test_section_defects_and_grid_sources(renv, settings):
    b = complete_job(renv, door="scratch", photos=1, settings=settings, fuel="petrol")
    src = source(b)
    d = one_page(
        {"type": "table", "source": {"kind": "section", "section": "inspection.section_1",
                                     "exclude": ["odometer"]}},
        {"type": "table", "source": {"kind": "section", "section": "inspection.gone"}},
        {"type": "table", "source": {"kind": "defects"}},
        {"type": "table", "source": {"kind": "grid", "columns": [{"label": "A"}, {"label": "B"}],
                                     "rows": [{"label": "{{ sys.booking_id }}", "cells": [
                                         {"field": "inspection.door"},
                                         {"field": "inspection.ghost", "fallback": "-"}]},
                                              {"label": "skip", "show_if": DENT, "cells": []},
                                              {"label": "blank", "cells": [
                                                  {"field": "inspection.ghost"}]}]}})
    parts = context.build(src, d)[0]["parts"]
    assert [r["label"] for r in parts[0]["rows"]] == ["Chassis number", "door", "engine_rating",
                                                     "dents"]
    assert parts[1]["source"]["kind"] == "defects"                   # empty section part dropped
    assert parts[1]["rows"] == [{"section": "Section 1", "label": "door", "text": "Scratch",
                                 "tone": "warn", "problem": True, "empty": False,
                                 "flags": ["problem", "warn", "minor"]}]
    assert parts[2]["rows"] == [{"label": "SA37926", "cells": [
        {"text": "Scratch", "tone": "warn", "problem": True, "flags": ["problem", "warn", "minor"]},
        {"text": "-", "tone": None, "problem": False, "flags": ["empty"]}]}]


def test_photo_grids_pick_issue_photos_and_captions(renv, settings):
    b = create(renv.ops, booking_id="PH1").json()
    assign(renv, b)
    start(renv.expert, b)
    door_pic = photo(renv, b, settings, field="door_photo")
    issue = photo(renv, b, settings, field="issue_pics")
    a1, a2 = photo(renv, b, settings), photo(renv, b, settings)
    body = {"client_submission_uuid": str(uuid.uuid4()), "answers": {"inspection": {
        "chassis_no": "MA3YPKCSKTJ273129", "door": "dent", "photo_a": [a1, a2],
        "door_photo": [door_pic], "issue_pics": [issue]}}}
    assert renv.expert.post(f"/api/v1/bookings/{b['id']}/submit", body,
                            format="json").status_code == 200
    src = source(b)

    def items(**part):
        d = one_page({"type": "photos", "hide_when_empty": False, **part})
        return [(i["media"], i["caption"] + (f": {i['answer']}" if i["answer"] else ""))
                for i in context.build(src, d)[0]["parts"][0]["items"]]

    assert items(source={"kind": "issues"}, caption="check") == [
        (door_pic, "door: Dent"), (issue, "issue_pics")]          # no check: its own label
    assert items(source={"kind": "section", "section": "inspection.section_1"}, which="first") == [
        (door_pic, "door_photo"), (a1, "photo_a")]
    assert items(source={"kind": "fields", "fields": ["inspection.photo_a"]}, which="issues") == []
    assert items(source={"kind": "fields", "fields": ["inspection.photo_a", "inspection.door"]},
                 caption="custom", caption_text="{{ sys.booking_id }}") == [
        (a1, "PH1"), (a2, "PH1")]
    assert items(source={"kind": "fields", "fields": ["inspection.photo_a"]},
                 caption="none")[0][1] == ""


def test_display_formats_every_field_type():
    from apps.forms.models import Field
    from apps.reports.context import display

    def f(t, **c):
        return Field(key="k", type=t, config=c)

    assert display(f("yes_no"), True) == ("Yes", None, False)
    assert display(f("multi_choice", options=CHOICES), ["ok", "dent"]) == ("Ok, Dent", "bad", True)
    assert display(f("single_choice", options=CHOICES), "gone") == ("gone", "ok", False)
    assert display(f("single_choice", options=CHOICES), "scratch")[1] == "warn"
    assert display(f("currency"), 1500) == ("₹1,500", None, False)
    assert display(f("currency"), 1499.5)[0] == "₹1,499.50"
    assert display(f("date"), "2026-10-14")[0] == "14-10-2026"
    assert display(f("datetime"), "2026-10-14T15:29:00+05:30")[0] == "14-10-2026 15:29"
    assert display(f("gps"), {"lat": 28.6, "lng": 77.2})[0] == "28.60000, 77.20000"
    assert display(f("photo"), ["a", "b"]) == ("", None, False)
    assert display(f("rating"), 4)[0] == "4/5"
    assert display(f("short_text"), "hello")[0] == "hello"
    assert display(f("number"), 7.5)[0] == "7.5" and display(f("number", unit="km"), 7)[0] == "7 km"
    assert display(None, "x") == ("", None, False) and display(f("short_text"), "")[0] == ""
    assert display(f("derived", true_label="Found", false_label="No"), False) == ("No", "ok", False)
    assert display(f("derived"), True) == ("Yes", "bad", True)


def test_user_pickers_and_master_lists_show_names(renv):
    from apps.accounts.models import User
    from apps.forms.models import Field
    from apps.reports.context import display

    user = User.objects.get(pk=renv.expert_user.pk)
    assert display(Field(key="k", type="user_picker", config={}), user.pk)[0] == (
        user.name or user.username)
    assert display(Field(key="k", type="user_picker", config={}), 999999)[0] == ""
    assert display(Field(key="k", type="master_list", config={"list": "city"}), "zz")[0] == "zz"


# ---------------------------------------------------------------- the HTML

def test_the_html_has_every_part_style_and_band(renv, settings):
    b = complete_job(renv, door="dent", photos=1, settings=settings)
    src = source(b, revision=3, token="tok-1")
    box = {"space_above": 2, "space_below": 1, "padding": 2, "border": "bottom",
           "border_color": "brand", "background": "warn", "round": True}
    d = {"schema": 2, "filename": "x.pdf",
         "paper": {"size": "Letter", "orientation": "landscape", "margins": {"left": 10}},
         "theme": {"colors": {"brand": "#123456"}, "size": 10},
         "bands": {"normal": {"header": {"left": [{"text": "<b>Hi {{ sys.booking_id }}</b>"},
                                                  {"image": "00000000-0000-0000-0000-000000000000"}],
                                         "background": "none"}},
                   "cover": {"footer": {"right": [{"text": "{{ sys.page }}/{{ sys.pages }}"}]}}},
         "pages": [
             {"title": "A", "style": "cover", "parts": [
                 {**table([{"field": "inspection.door"}, {"field": "inspection.odometer"},
                           {"field": "inspection.dents"}], title="Pairs"), "per_row": 2,
                  "look": {"header": True, "lines": "all", "height": "roomy", "stripes": False},
                  "box": box, "keep_together": True, "new_page": True, "keep_title": False},
                 {"type": "table", "source": {"kind": "defects"},
                  "look": {"header": False, "headers": ["S", "C", "R"]}},
                 {"type": "table", "source": {"kind": "grid", "columns": [
                     {"label": "Wide", "width": 40}, {"label": "Plain"}],
                     "rows": [{"label": "R", "cells": [{"field": "inspection.door"},
                                                       {"text": "x"}]}]}}]},
             {"title": "B", "style": "full", "parts": [
                 {"type": "photos", "per_row": 3, "shape": "original", "fit": "whole",
                  "frame": {"border": "brand", "round": False, "gap": 2}, "box": {"padding": 3},
                  "source": {"kind": "fields", "fields": ["inspection.photo_a"]}},
                 {"type": "text", "html": "<p>{{ inspection.odometer }}</p>", "columns": 2,
                  "size": "title", "align": "center"},
                 {"type": "verify", "size": 30}, {"type": "spacer", "height": 7},
                 {"type": "page_break"}]},
             {"title": "C", "parts": [
                 {"type": "photos", "fit": "top", "shape": "1:1",
                  "source": {"kind": "fields", "fields": ["inspection.door_photo"]}}]}]}
    html = render.render_html(context.build(src, d), d, src.values())
    for needle in ("Letter landscape", "--brand:#123456", "font-size: 10pt", "Hi SA37926",
                   "@page cover", "@page full { margin: 0; @top-center { content: none }", 'class="pageno"', 'class="pages"',
                   "chip tone-bad", "lines-all", "--pad:2.0mm", "border-bottom:0.4mm solid var(--brand)",
                   "background:var(--warn-tint)", "border-radius:2mm", "break-inside:avoid",
                   "break-before:page", "Section 1", 'style="width:40%"',
                   "object-fit:contain", "object-position:top", "cols2", "size-title",
                   "text-align:center", "tok-1", "height:7mm", 'class="pb"', "pg-full"):
        assert needle in html, needle
    assert "<thead>" in html and "part keep" not in html.split("Pairs")[0][-200:]
    assert "Photo not available" not in html


def test_missing_photos_and_pictures_render_a_gap(renv, settings):
    b = complete_job(renv, door="ok", photos=1, settings=settings)
    src = source(b)
    src.answers["inspection"]["photo_a"] = [str(uuid.uuid4())]          # never uploaded
    d = one_page({"type": "photos", "source": {"kind": "fields", "fields": ["inspection.photo_a"]}})
    d["watermark"] = {"image": "00000000-0000-0000-0000-000000000000"}
    html = render.render_html(context.build(src, d), d, src.values())
    assert "Photo not available" in html and "background: url" not in html


def test_logo_and_watermark_are_embedded_and_faded(renv):
    import base64

    from PIL import Image

    from apps.forms import assets

    buf = io.BytesIO()
    Image.new("RGBA", (40, 40), (166, 40, 48, 255)).save(buf, "PNG")
    pic = assets.create_asset(renv.admin_user, buf.getvalue())
    full = render.asset_uri(str(pic.id))
    faded = render.asset_uri(str(pic.id), 0.5)
    assert full and faded and full.startswith("data:image/png;base64,")
    img = Image.open(io.BytesIO(base64.b64decode(faded.split(",", 1)[1])))
    assert img.getpixel((5, 5)) == (166, 40, 48, 127)                  # half see-through
    assert render.asset_uri(str(uuid.uuid4())) is None


def test_photos_are_shrunk_once_for_print_and_previews_use_the_small_copy(renv, settings):
    from apps.media.models import MediaAsset

    b = create(renv.ops, booking_id="PR1").json()
    assign(renv, b)
    big = jpeg(w=2000, h=1500)
    init = renv.expert.post("/api/v1/media/initiate",
                            initiate_body(b["id"], big, field_key="photo_a"), format="json").json()
    renv.expert.post(f"/api/v1/media/{init['id']}/complete",
                     {"parts": put_parts(init, big, settings)}, format="json")
    asset = MediaAsset.objects.get(pk=init["id"])
    uri = render.print_image(str(asset.id))
    assert uri and storage.exists(f"print/{asset.id}-1000.jpg")
    assert render.print_image(str(asset.id)) == uri                   # the kept copy
    assert (render.print_image(str(asset.id), 480) or "").startswith("data:image/jpeg")  # preview
    asset.preview_key = ""
    asset.save()
    assert render.print_image(str(asset.id), 480)                     # no preview: shrunk here
    storage.put(asset.key, b"not a picture", "image/jpeg")
    assert render.print_image(str(asset.id), 300) is None
    assert render.print_image(str(uuid.uuid4())) is None


def test_the_renderer_loads_nothing_from_outside():
    html = ('<html><body><img src="file:///etc/passwd"><img src="http://example.com/x.png">'
            '<img src="http://169.254.169.254/latest/meta-data/">'
            '<div style="background-image:url(http://127.0.0.1:8000/x.png);height:20mm"></div>'
            '<link rel="stylesheet" href="https://example.com/x.css">'
            '<style>@import url("file:///etc/hosts");</style><p>ok</p></body></html>')
    pdf = render.render_pdf(html)
    assert pdf[:4] == b"%PDF"
    reader = pypdf.PdfReader(io.BytesIO(pdf))
    assert sum(len(p.images) for p in reader.pages) == 0


# ---------------------------------------------------------------- rendering end to end

def test_a_completed_booking_gets_a_pdf_automatically(renv, settings):
    set_template(renv)
    b = complete_job(renv, settings=settings)
    r = Report.objects.get(booking_id=b["id"])
    assert r.status == "ready" and r.revision == 1 and r.filename == "SA37926PDI.pdf"
    assert len(r.token) >= 32 and storage.exists(r.key) and r.template_version_id
    text, reader = pdf_text(b["id"])
    for needle in ("PRE DELIVERY CAR INSPECTION REPORT", "Booking ID", "SA37926", "Chassis Number",
                   "MA3YPKCSKTJ273129", "Driver Front Door", "Dent", "45 km", "OVERALL RATING",
                   "CAR PICTURES", "Please refer to the last page", "rev 1"):
        assert needle in text, needle
    assert "Page 1 of 2" in text and "Page 2 of 2" in text
    assert f"verify.carcid.in/{r.token}" in text
    assert len(reader.pages) == 2                                    # cover, then the detail page
    assert sum(len(p.images) for p in reader.pages) >= 4             # cover + 2 grid photos + QR
    for page in reader.pages:                                         # no blank pages
        assert "SA37926" in page.extract_text()


def test_no_template_means_no_report_but_the_booking_still_completes(env, settings):
    f = custom_form(env.admin, "pdi", "PDI")
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
    assert url["preview_url"].startswith("https://") and "attachment" not in url["preview_url"]


def test_regenerate_needs_permission_and_a_completed_booking(renv, settings):
    set_template(renv)
    b = create(renv.ops, booking_id="RG1").json()
    assert renv.ops.post(f"/api/v1/bookings/{b['id']}/report/regenerate").status_code == 409
    assert renv.expert.post(f"/api/v1/bookings/{b['id']}/report/regenerate").status_code == 403


def test_a_failing_render_is_retried_then_recorded_and_alerted(renv, settings, monkeypatch):
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
    assert body["car"] == "Maruti Victoris" and body["type"] == "PDI"
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


def test_publishing_a_template_works_without_a_booking_form_and_detects_stale_drafts(db, api_as):
    from apps.accounts.models import Role

    admin, _ = api_as(Role.ADMIN)
    form = admin.post("/api/v1/forms", {"key": "pdi", "name": "PDI"},
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


def test_a_real_logo_and_watermark_reach_the_page(renv, settings):
    from PIL import Image

    from apps.forms import assets

    buf = io.BytesIO()
    Image.new("RGBA", (40, 40), (166, 40, 48, 255)).save(buf, "PNG")
    pic = str(assets.create_asset(renv.admin_user, buf.getvalue()).id)
    b = complete_job(renv, door="ok", photos=1, settings=settings)
    src = source(b)
    d = definition.validate_definition({
        "schema": 2, "watermark": {"image": pic, "opacity": 0.3},
        "bands": {"normal": {"header": {"left": [{"image": pic, "height": 12}]}}},
        "pages": [{"title": "P", "parts": [
            {"type": "spacer", "show_if": DENT}, {"type": "text", "html": "<p>Hello</p>"}]}]})
    pages = context.build(src, d)
    assert [p["type"] for p in pages[0]["parts"]] == ["text"]         # the hidden part is gone
    html = render.render_html(pages, d, src.values())
    assert 'style="height:12mm"' in html and "@page { background: url(data:image/png" in html



def test_columns_contents_big_numbers_and_header_slots(renv, settings):
    from PIL import Image

    from apps.forms import assets

    buf = io.BytesIO()
    Image.new("RGBA", (40, 40), (166, 40, 48, 255)).save(buf, "PNG")
    pic = str(assets.create_asset(renv.admin_user, buf.getvalue()).id)
    b = complete_job(renv, door="dent", photos=1, settings=settings, fuel="petrol")
    src = source(b)
    d = definition.validate_definition({
        "schema": 2, "theme": {"fonts": {"body": "Helvetica", "headings": "Inter"}},
        "bands": {"normal": {"header": {
            "left": [{"image": pic, "tile": True}, {"text": "<strong>A</strong>"},
                     {"text": "<span class='small'>B</span>"}, {"image": pic},
                     {"image": "00000000-0000-0000-0000-000000000000"}]}}},
        "pages": [
            {"title": "Front", "style": "full", "parts": [{"type": "contents", "columns": 2}]},
            {"title": "One", "parts": [
                {"type": "columns", "align": "middle", "columns": [
                    {"width": 30, "parts": [table([{"field": "inspection.door"}],
                                                  look={"kv": True})]},
                    {"parts": [{"type": "photos", "caption": "check", "source": {
                        "kind": "fields", "fields": ["inspection.door_photo"]}}]},
                    {"parts": [table([{"field": "inspection.ghost"}])]}]},
                {"type": "columns", "columns": [{"parts": [table([{"field": "inspection.fuel"},
                                                                  {"field": "inspection.ghost"}])]},
                                                {"parts": []}]},
                {"type": "columns", "columns": [{"parts": []}, {"parts": []}]},     # dropped
                {"type": "table", "look": {"emphasis": True, "header": False}, "source": {
                    "kind": "grid", "columns": [{"label": "Engine"}, {"label": "Word"}],
                    "rows": [{"label": "", "cells": [{"field": "inspection.engine_rating"},
                                                     {"text": "{{ sys.checks }}"}]}]}}]},
            {"title": "Two", "parts": [{"type": "spacer"}]}]})
    assert definition.referenced_fields(d) >= {("inspection", "door_photo")}
    pages = context.build(src, d)
    assert [p["type"] for p in pages[1]["parts"]] == ["columns", "columns", "table"]
    html = render.render_html(pages, d, src.values())
    for needle in ('href="#pg-1">One', 'href="#pg-2">Two', "toc cols2", 'class="cols"',
                   "width:30.00%", "vertical-align:middle", "kv", "emphasis",
                   'class="big">4<small>/5</small>', '<i class="off"></i>', 'class="ans tone-bad"',
                   "logo tile", 'class="stack"', 'class="line"', "Helvetica, Arial, sans-serif;",
                   '"Inter", Helvetica'):
        assert needle in html, needle
    assert html.count('class="logo') == 2 and '<span class="big">' in html
    assert render.font_faces().count("@font-face") == 6
    sys_values = src.values()["sys"]
    assert sys_values["checks"] == "1" and sys_values["not_checked"] == "0"   # fuel is a fact
    unsure = source(b)
    unsure.answers["inspection"]["door"] = "not_checked"
    assert unsure.values()["sys"]["not_checked_list"] == "door"


def test_the_designer_previews_unsaved_edits_with_where_each_part_sits(renv, settings):
    import base64

    set_template(renv)
    b = complete_job(renv, settings=settings)
    draft = renv.admin.post(f"/api/v1/pdf-templates/{renv.template_id}/drafts").json()
    url = f"/api/v1/pdf-template-versions/{draft['id']}/preview"
    edited = one_page({**table([{"field": "inspection.door"}], title="Doors"), "id": "t1"},
                      {"type": "columns", "id": "c1", "columns": [
                          {"parts": [{**table([{"field": "inspection.odometer"}]), "id": "t2"}]},
                          {"parts": []}]})
    r = renv.admin.post(url, {"booking": b["id"], "definition": edited}, format="json")
    assert r.status_code == 200, r.json()
    body = r.json()
    assert base64.b64decode(body["pdf"])[:4] == b"%PDF" and body["filename"] == "SA37926.pdf"
    page = body["pages"][0]
    assert round(page["width"]) == 794 and {p["id"] for p in page["parts"]} == {"t1", "c1", "t2"}
    t1 = next(p for p in page["parts"] if p["id"] == "t1")
    assert t1["w"] > 0 and t1["h"] > 0
    bad = renv.admin.post(url, {"booking": b["id"], "definition": {"schema": 2}}, format="json")
    assert bad.status_code == 400 and bad.json()["code"] == "INVALID_TEMPLATE"


def test_the_designer_checks_lists_problems_and_fields_left_out(renv):
    url = f"/api/v1/pdf-template-versions/{renv.template_version_id}/checks"
    r = renv.admin.post(url, {"definition": one_page(
        table([{"field": "inspection.door"}, {"field": "inspection.ghost"}]),
        {"type": "table", "source": {"kind": "section", "section": "inspection.extra"}})},
        format="json")
    assert r.status_code == 200
    assert [i["code"] for i in r.json()["issues"]] == ["UNKNOWN_FIELD"]
    unused = [u["key"] for u in r.json()["unused"]]
    assert "odometer" in unused and "door" not in unused and "fuel" not in unused
    assert r.json()["unused"][0]["section"] == "Section 1"
    saved = renv.admin.post(url, {}, format="json")                       # the stored layout
    assert saved.status_code == 200 and saved.json()["issues"] == []
    bad = renv.admin.post(url, {"definition": []}, format="json")
    assert bad.status_code == 400


# ---------------------------------------------------------------- phase 4

@pytest.mark.parametrize("style", [
    "background-color:url(http://x/y.png)", "color:u\\rl(http://x/y.png)",
    "background-color:image-set('http://x/y.png' 1x)", "color:image(http://x/y.png)",
    "color:&#117;rl(http://x/y.png)", "background:url(http://x/y.png)", "content:url(x)"])
def test_custom_html_styles_never_load_anything(style):
    """Each one is refused, or nh3 drops the whole value: either way nothing is fetched."""
    d = one_page({"type": "html", "html": f'<div style="{style}">x</div>'})
    try:
        out = definition.validate_definition(d)["pages"][0]["parts"][0]["html"]
    except ValueError:
        return
    assert out == '<div style="">x</div>'


def test_custom_html_is_cleaned_filled_in_and_its_css_kept_inside_it(renv, settings):
    b = complete_job(renv, door="dent", photos=1, settings=settings, fuel="petrol")
    src = source(b)
    d = definition.validate_definition(one_page(
        {"type": "html", "css": "p { color: var(--brand) } .big { font-size: 20pt }",
         "html": '<div class="box" style="border:1px solid red" onclick="x()"><p>{{ '
                 'inspection.door }} {{ sys.booking_id }}</p><script>x()</script>'
                 '<img src="data:image/png;base64,AA"><a href="https://x.test">l</a>'
                 '<table><tr><td colspan="2">c</td></tr></table></div>'},
        {"type": "html", "html": "<p>no css</p>"}, {"type": "html", "html": "  "}))
    part = d["pages"][0]["parts"][0]
    assert "script" not in part["html"] and "img" not in part["html"] and "href" not in part["html"]
    out = definition.validate_definition(one_page({"type": "html", "html":
        '<p style="background-image:url(http://x);list-style-image:url(x);color:red">x</p>'}))
    assert out["pages"][0]["parts"][0]["html"] == '<p style="color:red">x</p>'   # pictures gone
    assert 'class="box"' in part["html"] and 'colspan="2"' in part["html"] and "onclick" not in part["html"]
    assert ("inspection", "door") in definition.referenced_fields(d)
    pages = context.build(src, d)
    assert len(pages[0]["parts"]) == 2                                   # the blank one hides
    html = render.render_html(pages, d, src.values())
    assert '<div class="custom custom-0">' in html and '<div class="custom custom-1">' in html
    assert ".custom-0 { p { color: var(--brand) } .big { font-size: 20pt } }" in html
    assert "<p>Dent SA37926</p>" in html
    render.render_pdf(html)


def test_style_rules_colour_and_bold_the_rows_they_match(renv, settings):
    b = complete_job(renv, door="dent", photos=1, settings=settings)
    src = source(b)
    rules = [{"when": "problem", "value": "warn"},
             {"when": "major", "label": "bad", "bold": True, "background": "bad"},
             {"when": "empty", "value": "muted", "background": "none"},
             {"when": "ok", "bold": False}]
    d = definition.validate_definition(one_page(
        table([{"field": "inspection.door"}, {"field": "inspection.fuel", "fallback": "-"},
               {"field": "inspection.odometer"}], style_rules=rules),
        table([{"field": "inspection.door"}], per_row=2, style_rules=rules),
        {"type": "table", "style_rules": rules, "source": {"kind": "defects"}},
        {"type": "table", "style_rules": rules, "source": {
            "kind": "grid", "columns": [{"label": "A"}, {"label": "B"}],
            "rows": [{"label": "x", "cells": [{"field": "inspection.door"},
                                              {"field": "inspection.ghost", "fallback": "-"}]}]}}))
    pages = context.build(src, d)
    rows = pages[0]["parts"][0]["rows"]
    assert rows[0]["flags"] == ["problem", "bad", "major"] and rows[1]["flags"] == ["empty"]
    html = render.render_html(pages, d, src.values())
    styled = '<td class="rb" style="background:var(--bad-tint)">'
    assert "<th class='l tone-bad rb' style=\"background:var(--bad-tint)\">door</th>" in html
    assert html.count(styled) >= 3
    assert '<span class="chip tone-warn">Dent</span>' in html             # problem -> warn
    assert '<span class="tone-muted">-</span>' in html                    # empty -> muted
    unsure = source(b)
    unsure.answers["inspection"]["door"] = "not_checked"
    assert "not_checked" in context.flags(unsure, "inspection.door", unsure.cell("inspection.door"))
    unsure.answers["inspection"]["door"] = ["scratch", "dent"]
    assert context.flags(unsure, "inspection.door", unsure.cell("inspection.door"))[-1] == "major"


def test_the_pdf_has_a_bookmark_for_each_page_and_part_title(renv, settings):
    b = complete_job(renv, door="dent", photos=1, settings=settings, fuel="petrol")
    src = source(b)
    d = {"schema": 2, "pages": [
        {"title": "Vehicle & owner", "parts": [table([{"field": "inspection.door"}], title="Body"),
                                               {"type": "text", "html": "<h2>Not a bookmark</h2>"}]},
        {"title": "", "parts": [table([{"field": "inspection.door"}])]}]}
    pdf = render.render_pdf(render.render_html(context.build(src, d), d, src.values()))
    reader = pypdf.PdfReader(io.BytesIO(pdf))
    outline: list = reader.outline
    assert outline[0].title == "Vehicle & owner" and [o.title for o in outline[1]] == ["Body"]
    assert len(outline) == 2 and (reader.metadata and reader.metadata.title or "").startswith("SA37926")


def test_the_designer_is_warned_about_blank_pages_and_headings_left_alone():
    html = ('<html><head><style>@page { size: A5 } .big { height: 168mm }</style></head><body>'
            '<p>one</p><div class="big"></div><h2>Alone</h2>'
            '<div style="break-before: page"></div>'
            '<div style="break-before: page"><h3>Last page heading</h3></div></body></html>')
    pdf, pages, checks = render.render_with_layout(html)
    assert pdf[:4] == b"%PDF" and len(pages) == 5      # the tall box spills onto page 2
    assert [(c["page"], c["code"]) for c in checks] == [
        (2, "BLANK_PAGE"), (3, "LONELY_HEADING"), (4, "BLANK_PAGE")]       # the last page is fine
    assert "“Alone”" in checks[1]["message"]
    ok = render.render_with_layout("<html><body><h2>T</h2><p>rows</p></body></html>")[2]
    assert ok == []
