"""Shared library of fields and sections: link/copy into forms, update-on-accept, archive."""
import pytest

from apps.accounts.models import AuditLog, Role

from .conftest import publish

pytestmark = pytest.mark.django_db

DEPTH: dict = {
    "key": "tyre_depth", "label": "Tyre depth", "type": "number", "helper_text": "Use gauge",
    "config": {"unit": "mm", "min": 0, "max": 20, "decimals": 1}}
TYRES: dict = {"title": "Tyres", "fields": [
    {"key": "depth_fl", "label": "Front left depth", "type": "number",
     "config": {"unit": "mm", "min": 0, "max": 20, "decimals": 1}, "required": True},
    {"key": "depth_fr", "label": "Front right depth", "type": "number",
     "config": {"unit": "mm", "min": 0, "max": 20, "decimals": 1}},
]}


def lib_field(admin, definition: dict = DEPTH):
    r = admin.post("/api/v1/library", {"kind": "field", "key": definition["key"],
                                       "definition": definition}, format="json")
    assert r.status_code == 201, r.json()
    return r.json()


def lib_section(admin, key="tyres", definition=TYRES):
    r = admin.post("/api/v1/library", {"kind": "section", "key": key, "definition": definition},
                   format="json")
    assert r.status_code == 201, r.json()
    return r.json()


@pytest.fixture
def draft(make_form, tree):
    """(version_id, page_id, section_id) of a fresh inspection form draft."""
    v = make_form()["draft_version"]["id"]
    page = tree(v)["pages"][0]
    return v, page["id"], page["sections"][0]["id"]


def find(tree_json, key):
    for p in tree_json["pages"]:
        for s in p["sections"]:
            for f in s["fields"]:
                if f["key"] == key:
                    return f
    raise KeyError(key)


def section_of(tree_json, title):
    return [s for p in tree_json["pages"] for s in p["sections"] if s["title"] == title][0]


def add_linked_field(admin, section_id, item, **extra):
    return admin.post(f"/api/v1/sections/{section_id}/fields/from-library",
                      {"library_item": item["id"], **extra}, format="json")


def add_linked_section(admin, page_id, item, **extra):
    return admin.post(f"/api/v1/pages/{page_id}/sections/from-library",
                      {"library_item": item["id"], **extra}, format="json")


# ---------------------------------------------------------------- creating items

def test_create_field_and_section_items(admin):
    f = lib_field(admin)
    assert f["kind"] == "field" and f["revision"] == 1 and f["archived"] is False
    s = lib_section(admin)
    assert s["kind"] == "section" and len(s["definition"]["fields"]) == 2


def test_duplicate_key_per_kind_rejected_but_kinds_are_separate(admin):
    lib_field(admin, {**DEPTH, "key": "tyres"})
    lib_section(admin, key="tyres")  # same key, other kind: fine
    r = admin.post("/api/v1/library", {"kind": "field", "key": "tyres",
                                       "definition": {**DEPTH, "key": "tyres"}}, format="json")
    assert r.status_code == 400


@pytest.mark.parametrize("definition,code", [
    ({**DEPTH, "config": {"min": 5, "max": 1}}, "INVALID_CONFIG"),
    ({**DEPTH, "type": "nope"}, "INVALID_CONFIG"),
    ({**DEPTH, "label": ""}, "INVALID_DEFINITION"),
    ({**DEPTH, "show_if": {"missing": ["inspection.x"]}}, "INVALID_RULE"),
    ({**DEPTH, "surprise": 1}, "INVALID_DEFINITION"),
    ({**DEPTH, "key": "other_key"}, "INVALID_DEFINITION"),  # must equal the item key
])
def test_invalid_field_definitions(admin, definition, code):
    r = admin.post("/api/v1/library", {"kind": "field", "key": "tyre_depth",
                                       "definition": definition}, format="json")
    assert r.status_code == 400 and r.json()["code"] == code


@pytest.mark.parametrize("definition,code", [
    ({"title": "", "fields": []}, "INVALID_DEFINITION"),
    ({"title": "T", "fields": [TYRES["fields"][0], TYRES["fields"][0]]}, "INVALID_DEFINITION"),
    ({"title": "T", "fields": [{**TYRES["fields"][0], "config": {"min": 9, "max": 1}}]},
     "INVALID_CONFIG"),
    ({"title": "T", "fields": [{**TYRES["fields"][0], "key": "Bad Key"}]}, "INVALID_KEY"),
    ({"title": "T"}, "INVALID_DEFINITION"),
])
def test_invalid_section_definitions(admin, definition, code):
    r = admin.post("/api/v1/library", {"kind": "section", "key": "tyres",
                                       "definition": definition}, format="json")
    assert r.status_code == 400 and r.json()["code"] == code


# ---------------------------------------------------------------- adding to forms

def test_add_field_linked(admin, draft, tree):
    v, _, s = draft
    item = lib_field(admin)
    r = add_linked_field(admin, s, item)
    assert r.status_code == 201
    f = find(tree(v), "tyre_depth")
    assert (f["label"], f["type"], f["helper_text"]) == ("Tyre depth", "number", "Use gauge")
    assert f["library"] == {"item": item["id"], "revision": 1, "update_available": False}
    assert f["locked"] is True


def test_add_field_as_copy_is_free_standing(admin, draft, tree):
    v, _, s = draft
    item = lib_field(admin)
    add_linked_field(admin, s, item, link=False)
    f = find(tree(v), "tyre_depth")
    assert f["library"] is None and f["locked"] is False
    assert admin.patch(f"/api/v1/fields/{f['id']}", {"label": "Depth"},
                       format="json").status_code == 200


def test_add_section_linked_materialises_fields(admin, draft, tree):
    v, page, _ = draft
    item = lib_section(admin)
    assert add_linked_section(admin, page, item).status_code == 201
    t = tree(v)
    sec = section_of(t, "Tyres")
    assert sec["library"]["item"] == item["id"] and sec["locked"] is True
    assert [f["key"] for f in sec["fields"]] == ["depth_fl", "depth_fr"]
    assert find(t, "depth_fl")["required"] is True  # definition default copied
    assert find(t, "depth_fl")["locked"] is True


def test_add_section_as_copy(admin, draft, tree):
    v, page, _ = draft
    add_linked_section(admin, page, lib_section(admin), link=False)
    sec = section_of(tree(v), "Tyres")
    assert sec["library"] is None and sec["locked"] is False
    assert find(tree(v), "depth_fl")["locked"] is False


def test_key_collision_when_adding(admin, draft, add_field):
    _, _, s = draft
    add_field(s, "tyre_depth")
    r = add_linked_field(admin, s, lib_field(admin))
    assert r.status_code == 400 and r.json()["code"] == "DUPLICATE_KEY"


def test_adding_to_a_published_version_is_blocked(admin, draft):
    v, page, s = draft
    item = lib_field(admin)
    publish(v)
    assert add_linked_field(admin, s, item).json()["code"] == "VERSION_PUBLISHED"
    assert add_linked_section(admin, page, lib_section(admin)).json()["code"] == "VERSION_PUBLISHED"


def test_archived_item_cannot_be_added_but_unknown_is_404(admin, draft):
    _, _, s = draft
    item = lib_field(admin)
    admin.patch(f"/api/v1/library/{item['id']}", {"archived": True}, format="json")
    r = add_linked_field(admin, s, item)
    assert r.status_code == 409 and r.json()["code"] == "ARCHIVED"
    assert add_linked_field(admin, s, {"id": 99999}).status_code == 404


def test_wrong_kind_rejected(admin, draft):
    v, page, s = draft
    sec_item = lib_section(admin)
    assert add_linked_field(admin, s, sec_item).status_code == 400
    assert add_linked_section(admin, page, lib_field(admin)).status_code == 400


# ---------------------------------------------------------------- locks and overrides

def test_linked_content_is_locked_but_per_form_settings_are_not(admin, draft, tree):
    v, _, s = draft
    add_linked_field(admin, s, lib_field(admin))
    f = find(tree(v), "tyre_depth")
    for body in ({"label": "x"}, {"helper_text": "x"}, {"config": {"unit": "cm"}}):
        r = admin.patch(f"/api/v1/fields/{f['id']}", body, format="json")
        assert r.status_code == 409 and r.json()["code"] == "LINKED_LOCKED"
    ok = admin.patch(f"/api/v1/fields/{f['id']}", {
        "required": True, "visible": False, "order": 7,
        "show_if": {"==": [{"var": "inspection.chassis_no"}, "x"]}}, format="json")
    assert ok.status_code == 200
    g = find(tree(v), "tyre_depth")
    assert g["required"] is True and g["visible"] is False and g["order"] == 7


def test_linked_section_structure_is_locked(admin, draft, tree, add_field):
    v, page, _ = draft
    add_linked_section(admin, page, lib_section(admin))
    t = tree(v)
    sec = section_of(t, "Tyres")
    assert admin.patch(f"/api/v1/sections/{sec['id']}", {"title": "x"},
                       format="json").json()["code"] == "LINKED_LOCKED"
    assert admin.patch(f"/api/v1/sections/{sec['id']}", {"visible": False, "order": 4},
                       format="json").status_code == 200
    assert add_field(sec["id"], "extra_one").json()["code"] == "LINKED_LOCKED"
    fl = find(t, "depth_fl")
    assert admin.delete(f"/api/v1/fields/{fl['id']}").json()["code"] == "LINKED_LOCKED"
    other = t["pages"][0]["sections"][0]["id"]
    r = admin.patch(f"/api/v1/fields/{fl['id']}", {"section": other}, format="json")
    assert r.status_code == 409 and r.json()["code"] == "LINKED_LOCKED"
    # per-form overrides on a field inside a linked section are allowed
    assert admin.patch(f"/api/v1/fields/{fl['id']}", {"required": False},
                       format="json").status_code == 200


def test_cannot_move_a_free_field_into_a_linked_section(admin, draft, tree, add_field):
    v, page, s = draft
    add_linked_section(admin, page, lib_section(admin))
    f = add_field(s, "my_field").json()
    sec = section_of(tree(v), "Tyres")
    r = admin.patch(f"/api/v1/fields/{f['id']}", {"section": sec["id"]}, format="json")
    assert r.status_code == 409 and r.json()["code"] == "LINKED_LOCKED"


def test_deleting_a_linked_field_or_section_removes_it_from_the_form(admin, draft, tree):
    v, page, s = draft
    add_linked_field(admin, s, lib_field(admin))
    add_linked_section(admin, page, lib_section(admin))
    f = find(tree(v), "tyre_depth")
    sec = section_of(tree(v), "Tyres")
    assert admin.delete(f"/api/v1/fields/{f['id']}").status_code == 204
    assert admin.delete(f"/api/v1/sections/{sec['id']}").status_code == 204
    assert "depth_fl" not in {x["key"] for x in
                              tree(v)["pages"][0]["sections"][0]["fields"]}


# ---------------------------------------------------------------- edits and updates

def edit(admin, item, **definition):
    r = admin.patch(f"/api/v1/library/{item['id']}",
                    {"definition": {**item["definition"], **definition}}, format="json")
    assert r.status_code == 200, r.json()
    return r.json()


def test_edit_bumps_revision_and_noop_does_not(admin):
    item = lib_field(admin)
    assert edit(admin, item, label="Tread depth")["revision"] == 2
    again = admin.patch(f"/api/v1/library/{item['id']}",
                        {"definition": {**item["definition"], "label": "Tread depth"}},
                        format="json").json()
    assert again["revision"] == 2


def test_key_and_type_are_immutable_in_the_library(admin):
    item = lib_field(admin)
    for change, code in (({"key": "other"}, "KEY_IMMUTABLE"),
                         ({"type": "short_text", "config": {}}, "TYPE_IMMUTABLE")):
        r = admin.patch(f"/api/v1/library/{item['id']}",
                        {"definition": {**item["definition"], **change}}, format="json")
        assert r.status_code == 400 and r.json()["code"] == code
    sec = lib_section(admin)
    changed = {**TYRES, "fields": [{**TYRES["fields"][0], "type": "short_text", "config": {}},
                                   TYRES["fields"][1]]}
    r = admin.patch(f"/api/v1/library/{sec['id']}", {"definition": changed}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "TYPE_IMMUTABLE"


def test_edit_shows_update_available_in_drafts_only(admin, draft, tree, make_form):
    v, _, s = draft
    item = lib_field(admin)
    add_linked_field(admin, s, item)
    edit(admin, item, label="Tread depth")
    f = find(tree(v), "tyre_depth")
    assert f["label"] == "Tyre depth"  # the draft keeps its snapshot until accepted
    assert f["library"]["update_available"] is True and f["library"]["revision"] == 1


def test_published_versions_never_change_and_report_no_update(admin, draft, tree):
    v, _, s = draft
    item = lib_field(admin)
    add_linked_field(admin, s, item)
    publish(v)
    edit(admin, item, label="Tread depth")
    f = find(tree(v), "tyre_depth")
    assert f["label"] == "Tyre depth" and f["library"]["update_available"] is False


def test_accept_update_on_a_field_keeps_per_form_settings(admin, draft, tree):
    v, _, s = draft
    item = lib_field(admin)
    add_linked_field(admin, s, item)
    f = find(tree(v), "tyre_depth")
    admin.patch(f"/api/v1/fields/{f['id']}", {"required": True, "order": 9}, format="json")
    edit(admin, item, label="Tread depth", helper_text="Gauge on the groove")
    r = admin.post(f"/api/v1/fields/{f['id']}/accept-update")
    assert r.status_code == 200
    g = find(tree(v), "tyre_depth")
    assert (g["label"], g["helper_text"]) == ("Tread depth", "Gauge on the groove")
    assert g["required"] is True and g["order"] == 9
    assert g["library"] == {"item": item["id"], "revision": 2, "update_available": False}


def test_accept_update_on_a_section_adds_removes_and_keeps_overrides(admin, draft, tree):
    v, page, _ = draft
    item = lib_section(admin)
    add_linked_section(admin, page, item)
    sec = section_of(tree(v), "Tyres")
    fl = find(tree(v), "depth_fl")
    admin.patch(f"/api/v1/fields/{fl['id']}", {"required": False}, format="json")
    new_fields = [{**TYRES["fields"][0], "label": "FL tread"},   # relabelled
                  {"key": "depth_rl", "label": "Rear left", "type": "number",
                   "config": {"unit": "mm"}}]                     # added; depth_fr removed
    edit(admin, item, title="Tyre set", fields=new_fields)
    assert section_of(tree(v), "Tyres")["library"]["update_available"] is True
    assert admin.post(f"/api/v1/sections/{sec['id']}/accept-update").status_code == 200
    t = tree(v)
    sec = section_of(t, "Tyre set")
    assert sorted(f["key"] for f in sec["fields"]) == ["depth_fl", "depth_rl"]
    assert find(t, "depth_fl")["label"] == "FL tread"
    assert find(t, "depth_fl")["required"] is False  # per-form override survived
    assert sec["library"]["revision"] == 2 and sec["library"]["update_available"] is False


def test_accept_update_when_up_to_date_is_a_noop(admin, draft, tree):
    v, _, s = draft
    add_linked_field(admin, s, lib_field(admin))
    f = find(tree(v), "tyre_depth")
    assert admin.post(f"/api/v1/fields/{f['id']}/accept-update").status_code == 200
    assert find(tree(v), "tyre_depth")["library"]["revision"] == 1


def test_accept_update_on_published_version_is_blocked(admin, draft, tree):
    v, _, s = draft
    item = lib_field(admin)
    add_linked_field(admin, s, item)
    f = find(tree(v), "tyre_depth")
    publish(v)
    edit(admin, item, label="X")
    r = admin.post(f"/api/v1/fields/{f['id']}/accept-update")
    assert r.status_code == 409 and r.json()["code"] == "VERSION_PUBLISHED"


def test_accept_update_on_unlinked_field_is_400(admin, draft, add_field):
    _, _, s = draft
    f = add_field(s, "plain").json()
    assert admin.post(f"/api/v1/fields/{f['id']}/accept-update").status_code == 400


def test_new_draft_keeps_links_and_snapshot_revisions(admin, make_form, tree):
    form = make_form()
    v = form["draft_version"]["id"]
    s = tree(v)["pages"][0]["sections"][0]["id"]
    item = lib_field(admin)
    add_linked_field(admin, s, item)
    publish(v)
    edit(admin, item, label="Tread depth")
    v2 = admin.post(f"/api/v1/forms/{form['id']}/drafts").json()["id"]
    f = find(tree(v2), "tyre_depth")
    assert f["label"] == "Tyre depth" and f["library"]["revision"] == 1
    assert f["library"]["update_available"] is True


# ---------------------------------------------------------------- archive / delete

def test_delete_in_use_is_409_and_archive_hides_without_breaking(admin, draft, tree):
    v, _, s = draft
    item = lib_field(admin)
    add_linked_field(admin, s, item)
    r = admin.delete(f"/api/v1/library/{item['id']}")
    assert r.status_code == 409 and r.json()["code"] == "IN_USE"
    admin.patch(f"/api/v1/library/{item['id']}", {"archived": True}, format="json")
    assert admin.get("/api/v1/library").json()["results"] == []
    assert len(admin.get("/api/v1/library?include_archived=1").json()["results"]) == 1
    assert find(tree(v), "tyre_depth")["library"]["item"] == item["id"]  # still linked
    edit_r = admin.patch(f"/api/v1/library/{item['id']}",
                         {"definition": {**item["definition"], "label": "Z"}}, format="json")
    assert edit_r.status_code == 200  # archived items can still be edited
    f = find(tree(v), "tyre_depth")
    assert admin.post(f"/api/v1/fields/{f['id']}/accept-update").status_code == 200


def test_unused_item_can_be_deleted(admin):
    item = lib_field(admin)
    assert admin.delete(f"/api/v1/library/{item['id']}").status_code == 204
    assert admin.get(f"/api/v1/library/{item['id']}").status_code == 404


def test_item_used_only_by_a_published_version_is_still_in_use(admin, draft):
    v, _, s = draft
    item = lib_field(admin)
    add_linked_field(admin, s, item)
    publish(v)
    assert admin.delete(f"/api/v1/library/{item['id']}").status_code == 409


def test_list_filters_and_search(admin):
    lib_field(admin)
    lib_section(admin)
    assert len(admin.get("/api/v1/library?kind=field").json()["results"]) == 1
    assert len(admin.get("/api/v1/library?kind=section").json()["results"]) == 1
    assert len(admin.get("/api/v1/library?q=tyre").json()["results"]) == 2
    assert len(admin.get("/api/v1/library?q=zzz").json()["results"]) == 0


def test_detail_lists_usages(admin, draft, make_form, tree):
    _, _, s = draft
    item = lib_field(admin)
    add_linked_field(admin, s, item)
    other = make_form("ppi")["draft_version"]["id"]
    add_linked_field(admin, tree(other)["pages"][0]["sections"][0]["id"], item, link=False)
    usages = admin.get(f"/api/v1/library/{item['id']}").json()["usages"]
    assert usages == [{"form": "pdi", "version": 1, "status": "draft"}]  # copies are not usages


# ---------------------------------------------------------------- save to library / unlink

def test_save_field_to_library_links_it(admin, draft, tree, add_field):
    v, _, s = draft
    f = add_field(s, "paint", type="number", config={"unit": "um"}, helper_text="h").json()
    r = admin.post(f"/api/v1/fields/{f['id']}/save-to-library", {}, format="json")
    assert r.status_code == 201
    item = r.json()
    assert item["kind"] == "field" and item["key"] == "paint" and item["revision"] == 1
    assert item["definition"]["config"] == {"unit": "um"}
    g = find(tree(v), "paint")
    assert g["library"]["item"] == item["id"] and g["locked"] is True
    again = admin.post(f"/api/v1/fields/{f['id']}/save-to-library", {}, format="json")
    assert again.status_code == 409  # already linked


def test_save_section_to_library_links_it(admin, draft, tree, add_field):
    v, page, _ = draft
    sec = admin.post(f"/api/v1/pages/{page}/sections", {"title": "Paint"}, format="json").json()
    add_field(sec["id"], "paint_fl")
    add_field(sec["id"], "paint_fr", required=True)
    r = admin.post(f"/api/v1/sections/{sec['id']}/save-to-library", {"key": "paint"},
                   format="json")
    assert r.status_code == 201
    item = r.json()
    assert item["kind"] == "section" and item["definition"]["title"] == "Paint"
    assert [f["key"] for f in item["definition"]["fields"]] == ["paint_fl", "paint_fr"]
    assert item["definition"]["fields"][1]["required"] is True
    assert section_of(tree(v), "Paint")["library"]["item"] == item["id"]


def test_save_section_with_system_fields_is_rejected(admin, draft):
    _, _, s = draft  # holds the system field chassis_no
    r = admin.post(f"/api/v1/sections/{s}/save-to-library", {"key": "sys"}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "SYSTEM_FIELD"


def test_unlink_makes_content_editable_again(admin, draft, tree):
    v, page, s = draft
    add_linked_field(admin, s, lib_field(admin))
    add_linked_section(admin, page, lib_section(admin))
    f = find(tree(v), "tyre_depth")
    sec = section_of(tree(v), "Tyres")
    assert admin.post(f"/api/v1/fields/{f['id']}/unlink").status_code == 200
    assert admin.post(f"/api/v1/sections/{sec['id']}/unlink").status_code == 200
    t = tree(v)
    assert find(t, "tyre_depth")["locked"] is False and find(t, "tyre_depth")["library"] is None
    assert section_of(t, "Tyres")["locked"] is False
    assert find(t, "depth_fl")["locked"] is False
    assert admin.patch(f"/api/v1/fields/{f['id']}", {"label": "free"},
                       format="json").status_code == 200
    assert admin.delete(f"/api/v1/library/{lib_section(admin, key='t2')['id']}").status_code == 204


def test_unlink_of_a_field_inside_a_linked_section_is_rejected(admin, draft, tree):
    v, page, _ = draft
    add_linked_section(admin, page, lib_section(admin))
    fl = find(tree(v), "depth_fl")
    r = admin.post(f"/api/v1/fields/{fl['id']}/unlink")
    assert r.status_code == 400  # unlink the section instead


# ---------------------------------------------------------------- access and audit

@pytest.mark.parametrize("role", [Role.OPS, Role.EXPERT])
def test_only_admin_writes_ops_reads_expert_cannot(api_as, admin, role, draft):
    _, _, s = draft
    item = lib_field(admin)
    client, _ = api_as(role)
    assert client.post("/api/v1/library", {"kind": "field", "key": "x_key",
                                           "definition": {**DEPTH, "key": "x_key"}},
                       format="json").status_code == 403
    assert client.patch(f"/api/v1/library/{item['id']}", {"archived": True},
                        format="json").status_code == 403
    assert client.delete(f"/api/v1/library/{item['id']}").status_code == 403
    assert client.post(f"/api/v1/sections/{s}/fields/from-library",
                       {"library_item": item["id"]}, format="json").status_code == 403
    expected = 200 if role == Role.OPS else 403
    assert client.get("/api/v1/library").status_code == expected


def test_library_actions_are_audited(admin, draft, tree):
    v, _, s = draft
    item = lib_field(admin)
    add_linked_field(admin, s, item)
    edit(admin, item, label="Tread depth")
    f = find(tree(v), "tyre_depth")
    admin.post(f"/api/v1/fields/{f['id']}/accept-update")
    admin.post(f"/api/v1/fields/{f['id']}/unlink")
    admin.patch(f"/api/v1/library/{item['id']}", {"archived": True}, format="json")
    actions = set(AuditLog.objects.values_list("action", flat=True))
    assert {"library.create", "library.update", "library.archive", "form.link_library",
            "form.accept_library_update", "form.unlink_library"} <= actions


# ---------------------------------------------------------------- remaining edge cases

def test_derived_fields_can_live_in_the_library(admin):
    d: dict = {"key": "dents_found", "label": "Dents found", "type": "derived", "config": {
        "rule": {"some": [{"var": "_defects"}, {"in": [{"var": ""}, ["inspection.door"]]}]},
        "true_label": "Found", "false_label": "Not Found"}}
    lib_field(admin, d)
    bad_rule = {**d, "key": "dents_two", "config": {**d["config"], "rule": {"missing": ["x"]}}}
    r = admin.post("/api/v1/library", {"kind": "field", "key": "dents_two",
                                       "definition": bad_rule}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "INVALID_RULE"


@pytest.mark.parametrize("patch", [{"required": "yes"}, {"visible": 1}, {"helper_text": 5}])
def test_flag_and_text_types_are_checked(admin, patch):
    r = admin.post("/api/v1/library", {"kind": "field", "key": "tyre_depth",
                                       "definition": {**DEPTH, **patch}}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "INVALID_DEFINITION"


def test_section_level_rule_and_key_are_validated(admin):
    r = admin.post("/api/v1/library", {"kind": "section", "key": "tyres", "definition": {
        **TYRES, "show_if": {"missing": ["x"]}}}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "INVALID_RULE"
    r = admin.post("/api/v1/library", {"kind": "section", "key": "Bad Key", "definition": TYRES},
                   format="json")
    assert r.status_code == 400 and r.json()["code"] == "INVALID_KEY"


def test_unknown_kind_is_rejected(admin):
    r = admin.post("/api/v1/library", {"kind": "page", "key": "x_y", "definition": {}},
                   format="json")
    assert r.status_code == 400 and r.json()["code"] == "INVALID_DEFINITION"


def test_rename_item_without_touching_the_definition(admin):
    item = lib_field(admin)
    r = admin.patch(f"/api/v1/library/{item['id']}", {"name": "Tread"}, format="json").json()
    assert r["name"] == "Tread" and r["revision"] == 1


def test_unlink_requires_a_link_and_system_fields_cannot_be_saved(admin, draft, tree, add_field):
    _, _, s = draft
    plain = add_field(s, "plain_one").json()
    r = admin.post(f"/api/v1/fields/{plain['id']}/unlink")
    assert r.status_code == 400 and r.json()["code"] == "NOT_LINKED"
    system = [f for f in tree(draft[0])["pages"][0]["sections"][0]["fields"]
              if f["key"] == "chassis_no"][0]
    r = admin.post(f"/api/v1/fields/{system['id']}/save-to-library", {}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "SYSTEM_FIELD"


def test_section_with_a_valid_show_if_is_accepted(admin, draft, tree):
    v, page, _ = draft
    rule = {"==": [{"var": "inspection.chassis_no"}, "x"]}
    item = lib_section(admin, key="conditional", definition={**TYRES, "show_if": rule})
    add_linked_section(admin, page, item)
    assert section_of(tree(v), "Tyres")["show_if"] == rule
