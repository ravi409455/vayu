"""Phase 5: picture library, shared themes and parts, copy, export and import, promotion."""
import io
from types import SimpleNamespace

import pytest
from PIL import Image

from apps.accounts.models import AuditLog
from apps.bookings.tests.conftest import custom_form
from apps.bookings.tests.test_submissions import publish_form
from apps.core.errors import CodedError
from apps.forms import assets, promote
from apps.forms.models import Form, FormAsset, FormVersion
from apps.reports import context, render, service, shared, tasks, transfer
from apps.reports.models import PdfTemplate, PdfTemplateVersion, SharedItem

from .test_reports import complete_job, one_page, renv, set_template, source, table  # noqa: F401

THEME = {"theme": {"colors": {"brand": "#123456"}},
         "bands": {"normal": {"header": {"left": [{"text": "<strong>SHARED HEAD</strong>"}]}}}}
DISCLAIMER = {"parts": [{"id": "x1", "type": "text", "html": "<p>Terms {{ inspection.door }}</p>"},
                        {"type": "columns", "columns": [{"parts": [{"id": "x2", "type": "spacer"}]},
                                                        {"parts": []}]}]}


def detail(e) -> dict:
    return e.value.detail  # a CodedError's payload


def png(color=(166, 40, 48)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (20, 20), color).save(buf, "PNG")
    return buf.getvalue()


def linked(theme_rev=1, snippet_rev=1, extra=()):
    return {"schema": 2, "theme_ref": {"key": "brand", "revision": theme_rev},
            "bands": {"normal": {"footer": {"left": [{"text": "own band, hidden by the theme"}]}}},
            "pages": [{"title": "P", "parts": [
                table([{"field": "inspection.door"}], id="t1"), *extra,
                {"id": "s1", "type": "snippet", "ref": {"key": "terms", "revision": snippet_rev}}]}]}


def second_template(env, key="ev", with_door=True):
    """Another inspection form (with a door check) and its template."""
    form = custom_form(env.admin, key, key.upper())
    v = form["draft_version"]["id"]
    sec = env.admin.get(f"/api/v1/form-versions/{v}").json()["pages"][0]["sections"][0]["id"]
    if with_door:
        env.admin.post(f"/api/v1/sections/{sec}/fields", {"key": "door", "label": "Door",
                       "type": "short_text"}, format="json")
    publish_form(env.admin, form["id"])
    return PdfTemplate.objects.get(pk=env.admin.post("/api/v1/pdf-templates", {
        "form": form["id"]}, format="json").json()["id"])


# ---------------------------------------------------------------- shared items

@pytest.mark.parametrize("kind,key,name,content", [
    ("colour", "k", "N", THEME), ("theme", "Bad Key", "N", THEME), ("theme", "k", " ", THEME),
    ("theme", "k", "N", {"pages": []}), ("theme", "k", "N", {"theme": {"size": 99}}),
    ("snippet", "k", "N", {"parts": [], "extra": 1}), ("snippet", "k", "N", []),
    ("snippet", "k", "N", {"parts": [{"type": "snippet", "ref": {"key": "a", "revision": 1}}]}),
    ("snippet", "k", "N", {"parts": [{"type": "nope"}]})])
def test_bad_shared_items_are_refused(renv, kind, key, name, content):
    with pytest.raises(CodedError) as e:
        shared.save(renv.admin_user, kind, key, name, content)
    assert detail(e)["code"] == "INVALID_SHARED"


def test_a_shared_save_moves_every_template_that_uses_it(renv):
    u = renv.admin_user
    shared.save(u, "theme", "brand", "Brand", THEME)
    shared.save(u, "snippet", "terms", "Terms", DISCLAIMER)
    item, updated = shared.save(u, "theme", "brand", "Brand", THEME)          # same: no-op
    assert item.revision == 1 and updated == []
    set_template(renv, linked())                                             # live v1
    pdi = PdfTemplate.objects.get(pk=renv.template_id)
    ev = second_template(renv)
    draft = ev.versions.get(status="draft")
    service.save_definition(u, draft, linked(), 0)                          # a draft only
    snip = SharedItem.objects.get(key="terms")
    assert [x["form"] for x in shared.usage(snip)] == ["EV", "PDI"]
    renv.admin.post(f"/api/v1/pdf-templates/{pdi.id}/drafts")              # pdi draft v2
    new = {"parts": [{"type": "text", "html": "<p>New terms</p>"}]}
    item, updated = shared.save(u, "snippet", "terms", "Terms 2", new)
    assert item.revision == 2 and updated == ["EV", "PDI"]
    assert ev.versions.get(status="draft").definition["pages"][0]["parts"][1]["ref"]["revision"] \
        == 2
    numbers = {v.number: (v.status, shared.uses(v.definition, "snippet", "terms"))
               for v in pdi.versions.all()}
    assert numbers == {1: ("published", 1), 2: ("published", 2), 3: ("draft", 2)}
    insp = SimpleNamespace(form_version=FormVersion.objects.filter(form_id=renv.form_id).last())
    live = tasks.published_template(None, insp)  # type: ignore[arg-type]
    assert live is not None and live.number == 2                       # reports use the new one
    shared.save(u, "theme", "brand", "Brand", {"theme": {"size": 10}})      # no draft: +1
    renv.admin.post(f"/api/v1/pdf-template-versions/{pdi.versions.get(status='draft').id}/"
                    "publish", {"row_version": pdi.versions.get(status="draft").row_version},
                    format="json")
    shared.save(u, "theme", "brand", "Brand", {"theme": {"size": 11}})
    assert pdi.versions.order_by("-number").values_list("number", flat=True)[0] == 5
    assert AuditLog.objects.filter(action="pdf_snippet.save").exists()


def test_a_shared_save_that_would_break_a_template_changes_nothing(renv):
    u = renv.admin_user
    shared.save(u, "theme", "brand", "Brand", THEME)
    shared.save(u, "snippet", "terms", "Terms", DISCLAIMER)
    set_template(renv, linked())
    second_template(renv, "ev", with_door=False)
    bad = {"parts": [table([{"field": "inspection.ghost"}])]}
    with pytest.raises(CodedError) as e:
        shared.save(u, "snippet", "terms", "Terms", bad)
    assert detail(e)["code"] == "SHARED_BLOCKED" and "ghost" in detail(e)["issues"][0]
    assert SharedItem.objects.get(key="terms").revision == 1


def test_resolve_fills_in_the_theme_and_shared_parts_and_reports_what_is_missing(renv, settings):
    u = renv.admin_user
    shared.save(u, "theme", "brand", "Brand", THEME)
    shared.save(u, "snippet", "terms", "Terms", DISCLAIMER)
    d = linked(extra=[{"id": "s2", "type": "snippet", "ref": {"key": "terms", "revision": 1}}])
    r = shared.resolve(d)
    assert "footer" not in r["bands"]["normal"] and r["theme"]["colors"]["brand"] == "#123456"
    inner = r["pages"][0]["parts"][1]["parts"]
    assert "id" not in inner[0] and "id" not in inner[1]["columns"][0]["parts"][0]
    assert d["pages"][0]["parts"][1].get("parts") is None                     # not changed
    gone = linked(theme_rev=7, snippet_rev=9)
    assert shared.resolve(gone)["pages"][0]["parts"][1]["parts"] == []
    assert "bands" not in shared.resolve(gone)
    t = PdfTemplate.objects.get(pk=renv.template_id)
    issues = service.definition_issues(t, gone)
    assert [(i["code"], i["path"], i["part"]) for i in issues] == [
        ("UNKNOWN_SHARED", "theme_ref", None), ("UNKNOWN_SHARED", "pages[0].parts[1]", "s1")]
    set_template(renv, d)
    b = complete_job(renv, door="dent", photos=1, settings=settings)
    tv = PdfTemplateVersion.objects.filter(template=t, status="published").latest("number")
    src = source(b)
    html = render.render_html(context.build(src, shared.resolve(tv.definition)),
                              shared.resolve(tv.definition), src.values())
    assert "SHARED HEAD" in html and html.count("Terms Dent") == 2 and "#123456" in html
    pdf, _ = tasks.build_pdf(src.booking, src.insp, tv, "t", 1, edge=480)
    assert pdf[:4] == b"%PDF"


def test_issues_name_their_part_and_the_closest_field(renv):
    t = PdfTemplate.objects.get(pk=renv.template_id)
    d = one_page(table([{"field": "inspection.dor"}], id="a"),
                 {"id": "b", "type": "table", "source": {"kind": "section",
                                                         "section": "inspection.sectoin_1"}},
                 table([{"field": "inspection.zzzzzz"}], id="c"))
    d["bands"] = {"normal": {"footer": {"left": [{"text": "{{ booking.nope }}"}]}}}
    issues = {i["ref"]: i for i in service.definition_issues(t, d)}
    assert issues["inspection.dor"]["part"] == "a" \
        and issues["inspection.dor"]["suggestion"] == "inspection.door"
    assert issues["inspection.sectoin_1"]["suggestion"] == "inspection.section_1"
    assert issues["inspection.zzzzzz"]["suggestion"] is None
    assert issues["booking.nope"]["path"] == "definition" and issues["booking.nope"]["part"] is None


# ---------------------------------------------------------------- pictures

def test_the_picture_library(renv):
    a = renv.admin
    up = a.post("/api/v1/pdf-pictures", {"file": io.BytesIO(png()), "name": "Logo"},
                format="multipart")
    assert up.status_code == 201 and up.json()["name"] == "Logo"
    again = a.post("/api/v1/pdf-pictures", {"file": io.BytesIO(png()), "name": "Logo 2"},
                   format="multipart")
    assert again.json()["id"] == up.json()["id"]                              # same picture, once
    plain = assets.create_asset(renv.admin_user, png((1, 2, 3)))              # an image field's
    named = assets.create_asset(renv.admin_user, png((1, 2, 3)), "Now named")
    assert named.id == plain.id and FormAsset.objects.get(pk=plain.id).name == "Now named"
    assert a.post("/api/v1/pdf-pictures", {"name": "x"}, format="multipart").status_code == 400
    assert [p["name"] for p in a.get("/api/v1/pdf-pictures").json()] == ["Logo", "Now named"]
    pid = up.json()["id"]
    assert a.patch(f"/api/v1/pdf-pictures/{pid}", {"name": " Brand logo "},
                   format="json").json()["name"] == "Brand logo"
    assert a.patch(f"/api/v1/pdf-pictures/{pid}", {"name": ""}, format="json").status_code == 400
    shared.save(renv.admin_user, "theme", "brand", "Brand", {"watermark": {"image": pid}})
    used = a.delete(f"/api/v1/pdf-pictures/{pid}")
    assert used.status_code == 409 and used.json()["code"] == "PICTURE_IN_USE"
    assert a.delete(f"/api/v1/pdf-pictures/{plain.id}").status_code == 204
    assert a.get(f"/api/v1/pdf-pictures/{plain.id}").status_code == 405
    assert a.delete(f"/api/v1/pdf-pictures/{plain.id}").status_code == 404


# ---------------------------------------------------------------- shared API, copy, files

def test_shared_items_api(renv):
    a = renv.admin
    made = a.post("/api/v1/pdf-shared", {"kind": "theme", "key": "brand", "name": "Brand",
                                         "content": THEME}, format="json")
    assert made.status_code == 201 and made.json()["revision"] == 1 \
        and made.json()["content"] == THEME and made.json()["updated"] == []
    a.post("/api/v1/pdf-shared", {"kind": "theme", "key": "brand", "name": "Brand",
                                  "content": {"theme": {"size": 10}}}, format="json")
    a.post("/api/v1/pdf-shared", {"kind": "snippet", "key": "terms", "name": "Terms",
                                  "content": DISCLAIMER}, format="json")
    assert [i["key"] for i in a.get("/api/v1/pdf-shared").json()] == ["terms", "brand"]
    assert [i["key"] for i in a.get("/api/v1/pdf-shared?kind=theme").json()] == ["brand"]
    pk = made.json()["id"]
    assert a.get(f"/api/v1/pdf-shared/{pk}").json()["content"] == {"theme": {"size": 10}}
    old = a.get(f"/api/v1/pdf-shared/{pk}?revision=1").json()
    assert old["content"] == THEME and old["revision"] == 1
    assert a.get(f"/api/v1/pdf-shared/{pk}?revision=x").status_code == 404
    bad = a.post("/api/v1/pdf-shared", {"kind": "theme"}, format="json")
    assert bad.status_code == 400 and bad.json()["code"] == "INVALID_SHARED"
    assert renv.ops.post("/api/v1/pdf-shared", {}, format="json").status_code == 403


def test_rename_and_delete_shared_items(renv):
    a = renv.admin
    theme = a.post("/api/v1/pdf-shared", {"kind": "theme", "key": "brand", "name": "Brand",
                                          "content": THEME}, format="json").json()
    a.post("/api/v1/pdf-shared", {"kind": "snippet", "key": "terms", "name": "Terms",
                                  "content": DISCLAIMER}, format="json")
    url = f"/api/v1/pdf-shared/{theme['id']}"
    r = a.patch(url, {"name": "  Car C.I.D. look "}, format="json")
    assert r.status_code == 200 and r.json()["name"] == "Car C.I.D. look"
    assert r.json()["key"] == "brand" and r.json()["revision"] == 1     # nothing else moves
    assert a.patch(url, {"name": " "}, format="json").json()["code"] == "INVALID_SHARED"
    assert renv.ops.patch(url, {"name": "x"}, format="json").status_code == 403
    assert renv.ops.delete(url).status_code == 403
    set_template(renv, linked(), publish=True)              # the template uses both
    used = a.delete(url)
    assert used.status_code == 409 and used.json()["code"] == "SHARED_IN_USE"
    assert "PDI" in used.json()["detail"]
    v = renv.admin.post(f"/api/v1/pdf-templates/{renv.template_id}/drafts", {}, format="json")
    assert v.status_code in (200, 201)
    draft = PdfTemplateVersion.objects.get(template_id=renv.template_id, status="draft")
    draft.definition = one_page(table([{"field": "inspection.door"}]))
    draft.save()
    assert a.delete(url).status_code == 409        # the live version (an old one later) uses it
    PdfTemplateVersion.objects.filter(template_id=renv.template_id).exclude(pk=draft.pk).delete()
    assert a.delete(url).status_code == 204 and not SharedItem.objects.filter(key="brand").exists()
    assert AuditLog.objects.filter(action__in=["pdf_theme.rename", "pdf_theme.delete"]).count() == 2


def test_copy_export_and_import(renv):
    a, u = renv.admin, renv.admin_user
    logo = assets.create_asset(u, png(), "Logo")
    shared.save(u, "theme", "brand", "Brand", {**THEME, "watermark": {"image": str(logo.id)}})
    shared.save(u, "snippet", "terms", "Terms", DISCLAIMER)
    d = linked()
    d["pages"][0]["parts"].append(table([{"field": "inspection.odometer"}], id="t2"))
    d["bands"] = {"normal": {"header": {"left": [{"image": str(logo.id)}]}}}
    set_template(renv, d)
    v = PdfTemplateVersion.objects.get(pk=renv.template_version_id)
    file = a.get(f"/api/v1/pdf-template-versions/{v.id}/export")
    assert "pdi-report-v1.json" in file["Content-Disposition"]
    body = file.json()
    assert body["kind"] == "vayu-report-template" and list(body["assets"]) == [str(logo.id)]
    assert [(i["kind"], i["key"]) for i in body["shared"]] == [("theme", "brand"),
                                                              ("snippet", "terms")]
    ev = second_template(renv)
    copied = a.post(f"/api/v1/pdf-templates/{renv.template_id}/copy",
                    {"form": Form.objects.get(key="ev").id}, format="json")
    assert copied.status_code == 409                                      # ev has one already
    other = custom_form(a, "uc", "Used")
    publish_form(a, other["id"])
    copied = a.post(f"/api/v1/pdf-templates/{renv.template_id}/copy", {"form": other["id"]},
                    format="json")
    assert copied.status_code == 201
    uc = PdfTemplate.objects.get(pk=copied.json()["id"])
    assert uc.versions.get().definition == d and uc.versions.get().status == "draft"

    # into ev: no draft there -> one is made; the theme here changed -> kept, with a note
    ev.versions.all().delete()
    shared.save(u, "theme", "brand", "Brand", {"theme": {"size": 12}})
    body["shared"].append({"kind": "snippet", "key": "fresh", "name": "Fresh", "revision": 4,
                           "content": {"parts": [{"type": "spacer"}]}})
    body["definition"]["pages"][0]["parts"].append(
        {"type": "snippet", "ref": {"key": "fresh", "revision": 4}})
    out = a.post(f"/api/v1/pdf-templates/{ev.id}/import", body, format="json")
    assert out.status_code == 200, out.json()
    got = out.json()
    assert got["status"] == "draft" and got["number"] == 1
    assert got["definition"]["theme_ref"] == {"key": "brand", "revision": 1}   # same content
    assert got["definition"]["pages"][0]["parts"][-1]["ref"] == {"key": "fresh", "revision": 1}
    assert got["notes"] == []
    assert [(i["ref"], i["suggestion"]) for i in got["issues"]] == [
        ("inspection.odometer", None)]
    assert got["definition"]["bands"]["normal"]["header"]["left"][0]["image"] == str(logo.id)
    # again, over the draft: replaced; a theme unlike any here -> this server's newest, noted
    body["shared"][0]["content"] = {"theme": {"size": 13}}
    again = a.post(f"/api/v1/pdf-templates/{ev.id}/import", body, format="json").json()
    assert again["row_version"] == 1 and again["definition"]["theme_ref"]["revision"] == 2
    assert again["notes"] == ["The shared theme 'Brand' is different here; kept this server's "
                              "version 2."]
    assert AuditLog.objects.filter(action="pdf_template.import").count() == 2
    for bad in ({}, {"kind": "vayu-report-template", "schema": 1},
                {"kind": "vayu-report-template", "schema": 2},
                {"kind": "vayu-report-template", "schema": 2, "definition": {"pages": 1}},
                {"kind": "vayu-report-template", "schema": 2, "definition": {}, "assets": {
                    "x": {"data": "!!"}}},
                {"kind": "vayu-report-template", "schema": 2, "definition": {}, "shared": [
                    {"kind": "theme"}]},
                {"kind": "vayu-report-template", "schema": 2, "definition": {}, "shared": [
                    {"kind": "theme", "key": "t", "name": "T", "revision": 1,
                     "content": {"pages": 1}}]}):
        r = a.post(f"/api/v1/pdf-templates/{ev.id}/import", bad, format="json")
        assert r.status_code == 400 and r.json()["code"] in ("INVALID_TEMPLATE_FILE",
                                                             "INVALID_BUNDLE"), (bad, r.json())
    assert renv.ops.post(f"/api/v1/pdf-templates/{ev.id}/import", body,
                         format="json").status_code == 403


def test_a_promotion_bundle_carries_the_template_pictures_and_shared_items(renv):
    u = renv.admin_user
    logo = assets.create_asset(u, png(), "Logo")
    shared.save(u, "theme", "brand", "Brand", {"watermark": {"image": str(logo.id)}})
    shared.save(u, "snippet", "terms", "Terms", DISCLAIMER)
    set_template(renv, linked())
    version = FormVersion.objects.filter(form_id=renv.form_id, status="published").latest("number")
    b = promote.export_bundle(version)
    assert b["pdf_template"]["assets"] and len(b["pdf_template"]["shared"]) == 2
    out = promote.import_bundle(u, b, as_new={"key": "pdi_copy", "name": "PDI copy"})
    t = PdfTemplate.objects.get(form_id=out["form"])
    d = t.versions.get().definition
    assert d["theme_ref"] == {"key": "brand", "revision": 1} and out["notes"] == []
    b["pdf_template"]["shared"][0]["content"] = {"pages": 1}
    with pytest.raises(CodedError) as e:
        promote.import_bundle(u, b, as_new={"key": "pdi_copy2", "name": "PDI copy 2"})
    assert detail(e)["code"] == "INVALID_BUNDLE"


def test_damaged_pictures_in_a_file(renv):
    with pytest.raises(CodedError) as e:
        # not base64 at all (a hex string can be valid base64 by chance, depending on its length)
        assets.import_from_bundle(renv.admin_user, {"data": "not base64!", "name": 5},
                                  library=True)
    assert detail(e)["code"] == "INVALID_BUNDLE"
    import base64

    a = assets.import_from_bundle(renv.admin_user, {"data": base64.b64encode(png()).decode(),
                                                    "name": None}, library=True)
    assert a.name == "Imported picture"
    assert transfer._images([{"image": 5}, {"x": {"image": "i"}}]) == {"i"}


def test_an_export_lists_each_shared_item_once_and_skips_missing_ones(renv):
    shared.save(renv.admin_user, "snippet", "terms", "Terms", DISCLAIMER)
    d = linked(extra=[{"id": "s2", "type": "snippet", "ref": {"key": "terms", "revision": 1}}])
    assert [i["key"] for i in transfer.export_payload(d)["shared"]] == ["terms"]   # no theme here
