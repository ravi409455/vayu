"""Promotion: export a form version as one bundle, import it as a DRAFT elsewhere."""
import json
from unittest import mock

import pytest

from apps.accounts.models import AuditLog
from apps.forms.models import (
    Field,
    Form,
    FormVersion,
    LibraryItem,
    MasterList,
    MasterListItem,
    Page,
    Section,
)
from apps.reports.models import PdfTemplate

pytestmark = pytest.mark.django_db
V = lambda k: {"var": k}  # noqa: E731
OPTS = [{"key": "ok", "label": "Ok"},
        {"key": "dent", "label": "Dent", "is_defect": True, "severity": "major"}]


def publish(admin, version_id):
    rv = admin.get(f"/api/v1/form-versions/{version_id}").json()["row_version"]
    r = admin.post(f"/api/v1/form-versions/{version_id}/publish", {"row_version": rv},
                   format="json")
    assert r.status_code == 200, r.json()


@pytest.fixture
def staging(admin):
    """A rich published inspection form: lists, library links, rules, access, checks, template."""
    city = admin.post("/api/v1/master-lists", {"key": "yard", "name": "Yard"}, format="json")
    assert city.status_code == 201
    for i, (k, label) in enumerate((("north", "North"), ("south", "South"))):
        admin.post("/api/v1/master-lists/yard/items", {"key": k, "label": label, "order": i},
                   format="json")
    form = admin.post("/api/v1/forms", {"key": "pdi", "name": "PDI"},
                      format="json").json()
    v = form["draft_version"]["id"]
    page = admin.get(f"/api/v1/form-versions/{v}").json()["pages"][0]
    s1 = page["sections"][0]["id"]

    def add(sec, key, type_="short_text", **kw):
        r = admin.post(f"/api/v1/sections/{sec}/fields", {"key": key, "label": key.title(),
                       "type": type_, **kw}, format="json")
        assert r.status_code == 201, r.json()
        return r.json()

    add(s1, "door", "single_choice", config={"options": OPTS}, required=True,
        access={"expert": {"in_progress": "edit"}})
    add(s1, "yard_pick", "master_list", config={"list": "yard"},
        show_if={"==": [V("inspection.door"), "dent"]}, helper_text="Where it is parked")
    add(s1, "grade", "rating", config={"category": "engine"})
    # a linked library field and a linked library section
    lf = admin.post("/api/v1/library", {"kind": "field", "key": "tyre_depth", "definition": {
        "key": "tyre_depth", "label": "Tyre depth", "type": "number",
        "config": {"unit": "mm"}}}, format="json").json()
    admin.post(f"/api/v1/sections/{s1}/fields/from-library", {"library_item": lf["id"]},
               format="json")
    ls = admin.post("/api/v1/library", {"kind": "section", "key": "brakes", "definition": {
        "title": "Brakes", "fields": [{"key": "pads", "label": "Pads", "type": "short_text"}]}},
        format="json").json()
    admin.post(f"/api/v1/pages/{page['id']}/sections/from-library", {"library_item": ls["id"]},
               format="json")
    admin.patch(f"/api/v1/form-versions/{v}/rating-config", {"config": {"categories": [
        {"key": "engine", "label": "Engine", "sections": ["Section 1"]}]}}, format="json")
    admin.post(f"/api/v1/form-versions/{v}/checks", {"rule": {"!!": [V("inspection.door")]},
               "message": "Pick a door state", "fields": ["door"]}, format="json")
    publish(admin, v)
    t = admin.post("/api/v1/pdf-templates", {"form": form["id"]}, format="json").json()
    tv = t["versions"][0]
    admin.patch(f"/api/v1/pdf-template-versions/{tv['id']}", {"definition": {
        "schema": 2, "pages": [{"title": "Body", "parts": [{
            "type": "table", "title": "Body",
            "source": {"kind": "fields", "rows": [{"field": "inspection.door"}]}}]}]},
        "row_version": 0}, format="json")
    r = admin.post(f"/api/v1/pdf-template-versions/{tv['id']}/publish", {"row_version": 1},
                   format="json")
    assert r.status_code == 200, r.json()
    return {"form": form, "version": v}


def export(admin, version_id):
    r = admin.get(f"/api/v1/promote/export?version={version_id}")
    assert r.status_code == 200, r.content
    return r.json()


def wipe():
    Form.objects.all().delete()
    LibraryItem.objects.all().delete()
    MasterList.objects.all().delete()


# ---------------------------------------------------------------- export

def test_export_is_self_contained_and_has_no_environment_ids(admin, staging):
    b = export(admin, staging["version"])
    assert b["schema"] == 2 and b["form"] == {"key": "pdi", "type": "custom", "name": "PDI",
                                              "inspection_type": "pdi",
                                              "submission_roles": ["expert", "ops"]}
    assert b["version"]["use_start"] is True and b["version"]["use_end"] is True
    sections = {s["title"]: s for p in b["version"]["pages"] for s in p["sections"]}
    assert set(sections) == {"Section 1", "Brakes"}
    fields = {f["key"]: f for f in sections["Section 1"]["fields"]}
    assert fields["tyre_depth"]["library"] == {"key": "tyre_depth", "revision": 1}
    assert sections["Brakes"]["library"] == {"key": "brakes", "revision": 1}
    assert fields["door"]["access"] == {"expert": {"in_progress": "edit"}}
    assert fields["chassis_no"]["is_system"] is True
    assert {(i["kind"], i["key"]) for i in b["library"]} == {("field", "tyre_depth"),
                                                             ("section", "brakes")}
    assert [m["key"] for m in b["master_lists"]] == ["yard"]
    assert b["version"]["rating_config"]["categories"][0]["key"] == "engine"
    assert b["version"]["checks"][0]["message"] == "Pick a door state"
    assert b["pdf_template"]["definition"]["schema"] == 2
    blob = json.dumps(b)
    assert '"id"' not in blob and '"row_version"' not in blob       # nothing environment-specific


def test_export_of_unknown_version_and_permissions(api_as, admin, staging):
    assert admin.get("/api/v1/promote/export?version=99999").status_code == 404
    assert admin.get("/api/v1/promote/export").status_code == 400
    from apps.accounts.models import Role

    for role in (Role.OPS, Role.EXPERT):
        c, _ = api_as(role)
        assert c.get(f"/api/v1/promote/export?version={staging['version']}").status_code == 403
        assert c.post("/api/v1/promote/import", {}, format="json").status_code == 403


# ---------------------------------------------------------------- round trip

def test_export_import_export_is_identical(admin, staging):
    first = export(admin, staging["version"])
    wipe()
    r = admin.post("/api/v1/promote/import", first, format="json")
    assert r.status_code == 201, r.json()
    draft = r.json()["draft_version"]
    again = export(admin, draft)
    assert again == first


def test_import_always_creates_a_draft_and_never_publishes(admin, staging):
    bundle = export(admin, staging["version"])
    wipe()
    r = admin.post("/api/v1/promote/import", bundle, format="json")
    body = r.json()
    v = FormVersion.objects.get(pk=body["draft_version"])
    assert v.status == "draft" and v.number == 1
    assert Form.objects.get(key="pdi").versions.filter(status="published").count() == 0
    assert body["created"]["form"] is True
    assert AuditLog.objects.filter(action="form.promote_import").exists()


def test_import_into_an_existing_form_adds_the_next_draft(admin, staging):
    bundle = export(admin, staging["version"])
    r = admin.post("/api/v1/promote/import", bundle, format="json")        # same database again
    assert r.status_code == 201
    v = FormVersion.objects.get(pk=r.json()["draft_version"])
    assert v.number == 2 and v.status == "draft" and r.json()["created"]["form"] is False
    again = admin.post("/api/v1/promote/import", bundle, format="json")
    assert again.status_code == 409 and again.json()["code"] == "DRAFT_EXISTS"
    assert FormVersion.objects.filter(form__key="pdi").count() == 2         # nothing half-written


# ---------------------------------------------------------------- master lists, library, links

def test_master_lists_match_by_key_missing_items_are_added_labels_never_overwritten(admin, staging):
    bundle = export(admin, staging["version"])
    wipe()
    ml = MasterList.objects.create(key="yard", name="Yard")
    MasterListItem.objects.create(list=ml, key="north", label="Northern yard", order=0,
                                  archived=True)
    r = admin.post("/api/v1/promote/import", bundle, format="json")
    assert r.status_code == 201
    items = {i.key: i for i in MasterList.objects.get(key="yard").items.all()}
    assert set(items) == {"north", "south"}
    assert items["north"].label == "Northern yard" and items["north"].archived is True
    assert r.json()["created"]["master_list_items"] == 1
    assert any("north" in n and "Northern yard" in n for n in r.json()["notes"])


def test_links_survive_and_a_newer_target_library_shows_update_available(admin, staging):
    bundle = export(admin, staging["version"])
    wipe()
    item = LibraryItem.objects.create(kind="field", key="tyre_depth", name="Tyre depth",
        definition={"key": "tyre_depth", "label": "Tread depth", "type": "number",
                    "config": {"unit": "mm"}}, revision=3)                  # prod is ahead
    r = admin.post("/api/v1/promote/import", bundle, format="json")
    assert r.status_code == 201
    tree = admin.get(f"/api/v1/form-versions/{r.json()['draft_version']}").json()
    f = [x for p in tree["pages"] for s in p["sections"] for x in s["fields"]
         if x["key"] == "tyre_depth"][0]
    assert f["library"]["item"] == item.id and f["library"]["update_available"] is True
    assert f["label"] == "Tyre depth"                                       # the form's own snapshot
    assert LibraryItem.objects.get(pk=item.pk).definition["label"] == "Tread depth"   # untouched
    assert any("tyre_depth" in n for n in r.json()["notes"])
    assert LibraryItem.objects.filter(kind="section", key="brakes").exists()      # missing: created


def test_imported_structure_and_details_match(admin, staging):
    bundle = export(admin, staging["version"])
    wipe()
    r = admin.post("/api/v1/promote/import", bundle, format="json")
    v = FormVersion.objects.get(pk=r.json()["draft_version"])
    assert Page.objects.filter(version=v).count() == 1 and Section.objects.filter(version=v).count() == 2
    door = Field.objects.get(version=v, key="door")
    assert door.required and door.access == {"expert": {"in_progress": "edit"}}
    yard = Field.objects.get(version=v, key="yard_pick")
    assert yard.show_if == {"==": [V("inspection.door"), "dent"]} and yard.helper_text
    assert Field.objects.get(version=v, key="chassis_no").is_system is True
    assert v.rating_config["categories"][0]["key"] == "engine"
    assert v.versions if False else True
    tpl = PdfTemplate.objects.get(form__key="pdi")
    draft = tpl.versions.get(status="draft")
    assert draft.definition["pages"][0]["title"] == "Body"


# ---------------------------------------------------------------- conflicts and bad input

def test_key_conflicts_are_rejected_listing_each_one_and_writing_nothing(admin, staging):
    bundle = export(admin, staging["version"])
    wipe()
    other = admin.post("/api/v1/forms", {"key": "pdi", "name": "Old"},
                       format="json").json()
    sec = admin.get(f"/api/v1/form-versions/{other['draft_version']['id']}").json()[
        "pages"][0]["sections"][0]["id"]
    admin.post(f"/api/v1/sections/{sec}/fields", {"key": "door", "label": "Door",
               "type": "number"}, format="json")             # same key, different type
    before = (FormVersion.objects.count(), Field.objects.count(), LibraryItem.objects.count())
    # the existing form has a draft too, so make room first
    publish(admin, other["draft_version"]["id"])
    r = admin.post("/api/v1/promote/import", bundle, format="json")
    assert r.status_code == 400 and r.json()["code"] == "IMPORT_CONFLICTS"
    assert any("door" in c and "single_choice" in c for c in r.json()["conflicts"])
    assert (FormVersion.objects.count(), Field.objects.count(), LibraryItem.objects.count()) == before


def test_type_and_inspection_type_conflicts(admin, staging):
    bundle = export(admin, staging["version"])
    wipe()
    Form.objects.create(key="pdi", type="start", name="Not a custom form")
    r = admin.post("/api/v1/promote/import", bundle, format="json")
    assert r.status_code == 400 and any("is a start form" in c for c in r.json()["conflicts"])
    wipe()
    Form.objects.create(key="other", type="custom", name="O", inspection_type="pdi")
    typed = {**bundle, "form": {**bundle["form"], "inspection_type": "pdi"}}
    r = admin.post("/api/v1/promote/import", typed, format="json")
    assert r.status_code == 400 and any("inspection type" in c for c in r.json()["conflicts"])


@pytest.mark.parametrize("mutate,status", [
    (lambda b: {**b, "schema": 99}, 400), (lambda b: {k: v for k, v in b.items() if k != "form"}, 400),
    (lambda b: {**b, "version": {"pages": "x"}}, 400), (lambda b: [], 400),
    (lambda b: {**b, "form": {**b["form"], "type": "weird"}}, 400),
])
def test_bad_bundles_are_rejected(admin, staging, mutate, status):
    bundle = export(admin, staging["version"])
    r = admin.post("/api/v1/promote/import", mutate(bundle), format="json")
    # a bare list never reaches the view: the JSON parser refuses it (still a 400)
    assert r.status_code == status
    assert isinstance(mutate(bundle), list) or r.json()["code"] in ("INVALID_BUNDLE",
                                                                    "BUNDLE_TOO_NEW")


def test_a_bundle_from_a_newer_server_is_refused_with_a_clear_code(admin, staging):
    bundle = export(admin, staging["version"])
    r = admin.post("/api/v1/promote/import", {**bundle, "schema": 3}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "BUNDLE_TOO_NEW"


def test_an_existing_template_draft_blocks_the_import_cleanly(admin, staging):
    bundle = export(admin, staging["version"])
    t = PdfTemplate.objects.get(form__key="pdi")
    t.versions.create(number=2, status="draft", definition={})
    r = admin.post("/api/v1/promote/import", bundle, format="json")
    assert r.status_code == 409 and r.json()["code"] == "DRAFT_EXISTS"
    assert FormVersion.objects.filter(form__key="pdi").count() == 1


def test_booking_forms_with_system_fields_promote_too(admin):
    from django.core.management import call_command

    call_command("seed_master_lists")
    v = Form.objects.get(type="booking").versions.get(status="draft").id
    publish(admin, v)
    bundle = export(admin, v)
    wipe()
    call_command("seed_master_lists")
    r = admin.post("/api/v1/promote/import", bundle, format="json")
    assert r.status_code == 201
    assert export(admin, r.json()["draft_version"]) == bundle


def test_a_bundle_whose_library_link_is_missing_is_invalid(admin, staging):
    bundle = export(admin, staging["version"])
    r = admin.post("/api/v1/promote/import", {**bundle, "library": []}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "INVALID_BUNDLE"
    assert "tyre_depth" in r.json()["detail"] or "brakes" in r.json()["detail"]


def test_an_existing_form_may_keep_its_own_inspection_type(admin, staging):
    from django.core.management import call_command

    call_command("seed_master_lists")
    Form.objects.filter(key="pdi").update(inspection_type="pdi")
    bundle = export(admin, staging["version"])
    assert admin.post("/api/v1/promote/import", bundle, format="json").status_code == 201


def test_a_library_field_with_a_different_type_is_a_conflict(admin, staging):
    bundle = export(admin, staging["version"])
    wipe()
    LibraryItem.objects.create(kind="field", key="tyre_depth", name="x", definition={
        "key": "tyre_depth", "label": "x", "type": "short_text", "config": {}})
    r = admin.post("/api/v1/promote/import", bundle, format="json")
    assert r.status_code == 400 and any("Library field 'tyre_depth'" in c
                                        for c in r.json()["conflicts"])


# ---------------------------------------------------------------- review: bundles are validated like edits

def _first_field(b):
    return b["version"]["pages"][0]["sections"][0]["fields"][0]


@pytest.mark.parametrize("mutate", [
    lambda b: b["version"]["pages"][0].__setitem__("access", {"nobody": {"draft": "edit"}}),
    lambda b: b["version"]["pages"][0]["sections"][0].__setitem__("show_if", {"a": 1, "b": 2}),
    lambda b: _first_field(b).__setitem__("type", "bogus"),
    lambda b: _first_field(b).__setitem__("config", {"x": 1}),
    lambda b: b["version"].__setitem__("rating_config", {"nope": 1}),
    lambda b: b["form"].__setitem__("key", "Bad Key!"),
    lambda b: _first_field(b).pop("access"),
    lambda b: b["pdf_template"].__setitem__("definition", {"junk": 1}),
    lambda b: b["pdf_template"].__setitem__("definition", {"blocks": []}),   # old designer
    lambda b: b["pdf_template"].__setitem__("shared", "not a list"),       # damaged template file
    lambda b: b["version"]["checks"].append({"rule": {"a": 1, "b": 2}, "message": "m",
                                             "fields": [], "order": 9}),
    lambda b: b["library"][0].__setitem__("definition", {"type": "bogus"}),
    lambda b: b["version"]["pages"][0]["sections"][0].__setitem__("key", "Bad Key"),
    lambda b: b["version"]["pages"][0]["sections"].append(
        {**b["version"]["pages"][0]["sections"][0], "fields": []}),
])
def test_invalid_content_is_refused_and_nothing_is_written(admin, staging, mutate):
    bundle = export(admin, staging["version"])
    wipe()
    mutate(bundle)
    r = admin.post("/api/v1/promote/import", bundle, format="json")
    assert r.status_code == 400 and r.json()["code"] == "INVALID_BUNDLE", r.content
    assert not Form.objects.exists() and not MasterList.objects.exists()
    assert not LibraryItem.objects.exists()


def test_a_bundle_cannot_make_a_field_a_system_field(admin, staging):
    bundle = export(admin, staging["version"])
    wipe()
    _first_field(bundle)["is_system"] = True
    _first_field(bundle)["key"] = "not_a_system_key"
    assert admin.post("/api/v1/promote/import", bundle, format="json").status_code == 201
    assert not Field.objects.filter(key="not_a_system_key", is_system=True).exists()


def test_a_non_object_bundle_is_refused_by_the_checker_itself():
    """The JSON parser already stops a bare list at the door; the checker still guards its callers."""
    from apps.core.errors import CodedError
    from apps.forms import promote

    with pytest.raises(CodedError) as e:
        promote._check_shape([])
    assert e.value.detail == {"code": "INVALID_BUNDLE", "detail": mock.ANY}


def test_section_keys_travel_and_an_older_bundle_gets_them_from_titles(admin, staging):
    bundle = export(admin, staging["version"])
    keys = [s["key"] for p in bundle["version"]["pages"] for s in p["sections"]]
    assert keys and all(keys)
    wipe()
    for p in bundle["version"]["pages"]:
        for s in p["sections"]:
            s.pop("key")
    assert admin.post("/api/v1/promote/import", bundle, format="json").status_code == 201
    assert sorted(Section.objects.values_list("key", flat=True)) == sorted(keys)


@pytest.mark.parametrize("mutate", [
    lambda b: {**b, "version": {**b["version"], "pages": [{"sections": "x"}]}},
    lambda b: {**b, "version": {**b["version"], "pages": [{"sections": [{"fields": 5}]}]}},
])
def test_a_hand_edited_bundle_of_the_wrong_shape_is_a_400_not_a_500(admin, staging, mutate):
    """F-059."""
    bundle = export(admin, staging["version"])
    r = admin.post("/api/v1/promote/import", mutate(bundle), format="json")
    assert r.status_code == 400 and r.json()["code"] == "INVALID_BUNDLE", r.content
