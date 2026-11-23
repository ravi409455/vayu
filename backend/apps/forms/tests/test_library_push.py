"""The library as the control point: revisions and history, self-contained items, ownership on
update, and pushing a new revision to every form that uses it, all or nothing."""
import pytest

from apps.accounts.models import AuditLog, Role
from apps.forms.models import Field, Form, FormVersion, LibraryItem, LibraryRevision

from .test_library import (
    DEPTH,
    TYRES,
    add_linked_field,
    add_linked_section,
    edit,
    find,
    lib_field,
    lib_section,
    rev,
    section_of,
)
from .test_promote import publish

pytestmark = pytest.mark.django_db


def new_form(make_form, tree, key):
    f = make_form(key=key)
    v = f["draft_version"]["id"]
    p = tree(v)["pages"][0]
    return f, v, p["id"], p["sections"][0]["id"]


# ---------------------------------------------------------------- revisions and history

def test_every_save_is_a_revision_with_who_and_what_changed(admin):
    item = lib_field(admin)
    edit(admin, item, label="Tread depth", required=True)
    rows = list(LibraryRevision.objects.filter(item_id=item["id"]).order_by("revision"))
    assert [r.revision for r in rows] == [1, 2]
    assert rows[1].changed_keys == ["label", "required"] and rows[1].by
    history = admin.get(f"/api/v1/library/{item['id']}/history").json()
    assert [h["revision"] for h in history] == [2, 1]                  # newest first
    assert history[1]["definition"]["label"] == "Tyre depth"           # restorable later


def test_a_save_from_an_old_revision_is_refused_and_a_missing_revision_too(admin):
    item = lib_field(admin)
    edit(admin, item, label="First")
    stale = admin.patch(f"/api/v1/library/{item['id']}", {
        "definition": {**item["definition"], "label": "Second"}, "revision": 1}, format="json")
    assert stale.status_code == 409 and stale.json()["code"] == "STALE_LIBRARY_ITEM"
    assert stale.json()["revision"] == 2
    none = admin.patch(f"/api/v1/library/{item['id']}", {
        "definition": {**item["definition"], "label": "Third"}}, format="json")
    assert none.status_code == 400 and none.json()["code"] == "REVISION_REQUIRED"
    assert LibraryItem.objects.get(pk=item["id"]).definition["label"] == "First"


def test_section_history_names_the_fields_that_changed(admin):
    item = lib_section(admin)
    new_fields = [{**TYRES["fields"][0], "label": "FL"}, TYRES["fields"][1]]
    edit(admin, item, title="Tyre set", fields=new_fields)
    row = LibraryRevision.objects.get(item_id=item["id"], revision=2)
    assert row.changed_keys == ["section.title", "depth_fl"]
    swapped = [TYRES["fields"][1], new_fields[0]]
    edit(admin, item, title="Tyre set", fields=swapped)
    last = LibraryRevision.objects.get(item_id=item["id"], revision=3)
    assert last.changed_keys == ["order"]


def test_rename_in_the_name_field_alone_does_not_make_a_revision(admin):
    item = lib_field(admin)
    r = admin.patch(f"/api/v1/library/{item['id']}", {"name": "Tread"}, format="json")
    assert r.status_code == 200 and r.json()["revision"] == 1


# ---------------------------------------------------------------- self-contained items

def test_a_rule_may_use_the_items_own_fields_and_system_fields(admin):
    ok = {"title": "Brakes", "show_if": {"==": [{"var": "booking.city"}, "delhi"]}, "fields": [
        {"key": "pads", "label": "Pads", "type": "yes_no"},
        {"key": "pads_note", "label": "Note", "type": "short_text",
         "show_if": {"==": [{"var": "inspection.pads"}, False]}},
        {"key": "chassis_seen", "label": "Seen", "type": "yes_no",
         "required_if": {"!!": [{"var": "inspection.chassis_no"}]}}]}
    assert admin.post("/api/v1/library", {"kind": "section", "key": "brakes", "definition": ok},
                      format="json").status_code == 201


@pytest.mark.parametrize("where", ["field", "section_rule", "derived", "required_if"])
def test_a_rule_that_needs_another_field_is_refused_with_what_to_do(admin, where):
    outside = {"==": [{"var": "inspection.door"}, "dent"]}
    if where == "field":
        body = {"kind": "field", "key": "gap", "definition": {
            "key": "gap", "label": "Gap", "type": "short_text", "show_if": outside}}
    elif where == "required_if":
        body = {"kind": "field", "key": "gap", "definition": {
            "key": "gap", "label": "Gap", "type": "short_text", "required_if": outside}}
    elif where == "section_rule":
        body = {"kind": "section", "key": "gaps", "definition": {
            "title": "Gaps", "show_if": outside, "fields": []}}
    else:
        body = {"kind": "field", "key": "gap", "definition": {
            "key": "gap", "label": "Gap", "type": "derived",
            "config": {"rule": {"!!": [{"var": "booking.nonsense_key"}]},
                       "true_label": "Y", "false_label": "N"}}}
    r = admin.post("/api/v1/library", body, format="json")
    assert r.status_code == 400 and r.json()["code"] == "RULE_NOT_SELF_CONTAINED"
    assert "same library section" in r.json()["detail"]


def test_the_defect_counter_and_today_are_not_outside_fields(admin):
    d = {"key": "dents", "label": "Dents", "type": "derived", "config": {
        "rule": {"some": [{"var": "_defects"}, {"==": [{"var": ""}, "inspection.dents"]}]},
        "true_label": "Y", "false_label": "N"}}
    assert admin.post("/api/v1/library", {"kind": "field", "key": "dents", "definition": d},
                      format="json").status_code == 201


def test_an_edit_that_breaks_self_containment_is_refused_too(admin):
    item = lib_field(admin)
    r = admin.patch(f"/api/v1/library/{item['id']}", {"definition": {
        **item["definition"], "show_if": {"!!": [{"var": "inspection.door"}]}},
        "revision": 1}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "RULE_NOT_SELF_CONTAINED"


# ---------------------------------------------------------------- the library owns the item

def test_a_section_item_carries_its_access_and_the_form_receives_it(admin, make_form, tree):
    access = {"expert": {"in_progress": "hidden"}}
    item = lib_section(admin, key="locked", definition={**TYRES, "access": access})
    f, v, page, _ = new_form(make_form, tree, "pdi")
    add_linked_section(admin, page, item)
    assert section_of(tree(v), "Tyres")["access"] == access
    edit(admin, item, access={})
    sec = section_of(tree(v), "Tyres")
    assert admin.post(f"/api/v1/sections/{sec['id']}/accept-update").status_code == 200
    assert section_of(tree(v), "Tyres")["access"] == {}
    assert f


def test_renaming_a_linked_section_through_the_library_keeps_its_rating(admin, make_form, tree):
    item = lib_section(admin)
    f, v, page, _ = new_form(make_form, tree, "pdi")
    add_linked_section(admin, page, item)
    admin.patch(f"/api/v1/form-versions/{v}/rating-config", {"config": {"categories": [
        {"key": "tyres", "label": "Tyres", "sections": ["Tyres", "Other"]}]}}, format="json")
    edit(admin, item, title="Tyre set")
    sec = section_of(tree(v), "Tyres")
    admin.post(f"/api/v1/sections/{sec['id']}/accept-update")
    cats = tree(v)["rating_config"]["categories"]
    assert cats == [{"key": "tyres", "label": "Tyres", "sections": ["Tyre set", "Other"]}]
    assert f


def test_renaming_a_section_by_hand_updates_the_rating_categories(admin, make_form, tree):
    f, v, _, sec = new_form(make_form, tree, "pdi")
    admin.patch(f"/api/v1/form-versions/{v}/rating-config", {"config": {"categories": [
        {"key": "body", "label": "Body", "sections": ["Section 1"]}]}}, format="json")
    assert admin.patch(f"/api/v1/sections/{sec}", {"title": "Bodywork"},
                       format="json").status_code == 200
    assert tree(v)["rating_config"]["categories"][0]["sections"] == ["Bodywork"]
    assert admin.patch(f"/api/v1/sections/{sec}", {"visible": True}, format="json").status_code == 200
    assert f


# ---------------------------------------------------------------- pushing

def linked_form(admin, make_form, tree, key, item, *, publish_it=False):
    f, v, page, sec = new_form(make_form, tree, key)
    assert add_linked_field(admin, sec, item).status_code == 201
    if publish_it:
        publish(admin, v)
    return f, v


def push_preview(admin, item):
    r = admin.post(f"/api/v1/library/{item['id']}/push-preview")
    assert r.status_code == 200, r.content
    return r.json()


def push(admin, item, **body):
    return admin.post(f"/api/v1/library/{item['id']}/push",
                      {"revision": rev(item), **body}, format="json")


def test_the_preview_lists_every_form_and_each_setting_that_changes_and_writes_nothing(
        admin, make_form, tree):
    item = lib_field(admin)
    a, va = linked_form(admin, make_form, tree, "pdi", item)                      # open draft
    b, vb = linked_form(admin, make_form, tree, "ev", item, publish_it=True)      # live only
    c, _ = linked_form(admin, make_form, tree, "old", item)
    Form.objects.filter(pk=c["id"]).update(is_active=False)
    edit(admin, item, label="Tread depth", required=True)
    before = (FormVersion.objects.count(), Field.objects.count(), AuditLog.objects.count())
    out = push_preview(admin, item)
    assert (FormVersion.objects.count(), Field.objects.count(), AuditLog.objects.count()) == before
    by_form = {f["form"]: f for f in out["forms"]}
    assert set(by_form) == {"pdi", "ev"} and out["skipped"] == [
        {"form": "old", "reason": "inactive"}]
    assert by_form["pdi"]["state"] == "draft" and by_form["ev"]["state"] == "published_only"
    changes = {(c["setting"], str(c["from"]), str(c["to"])) for c in by_form["pdi"]["changes"]}
    assert changes == {("label", "Tyre depth", "Tread depth"), ("required", "False", "True")}
    assert out["blocked"] is False
    assert a and b and va and vb


def test_a_push_updates_drafts_in_place_and_makes_a_new_draft_for_live_only_forms(
        admin, make_form, tree):
    item = lib_field(admin)
    a, va = linked_form(admin, make_form, tree, "pdi", item)
    b, vb = linked_form(admin, make_form, tree, "ev", item, publish_it=True)
    edit(admin, item, label="Tread depth")
    r = push(admin, item)
    assert r.status_code == 200 and r.json()["blocked"] is False
    assert find(tree(va), "tyre_depth")["label"] == "Tread depth"           # same draft
    forms_b = FormVersion.objects.filter(form_id=b["id"]).order_by("number")
    assert [v.status for v in forms_b] == ["published", "draft"]            # live one untouched
    new_draft = forms_b[1]
    assert find(tree(new_draft.id), "tyre_depth")["label"] == "Tread depth"
    assert find(tree(vb), "tyre_depth")["label"] == "Tyre depth"
    assert AuditLog.objects.filter(action="library.push").count() == 1


def test_a_form_already_up_to_date_is_left_alone(admin, make_form, tree):
    item = lib_field(admin)
    linked_form(admin, make_form, tree, "pdi", item)
    assert push_preview(admin, item)["forms"] == []
    assert push(admin, item).json()["forms"] == []


def test_the_push_is_blocked_while_any_problem_exists_and_nothing_changes(admin, make_form, tree):
    item = lib_section(admin)
    f, v, page, _ = new_form(make_form, tree, "pdi")
    add_linked_section(admin, page, item)
    publish(admin, v)
    t = admin.post("/api/v1/pdf-templates", {"form": f["id"]}, format="json").json()
    tv = t["versions"][0]
    admin.patch(f"/api/v1/pdf-template-versions/{tv['id']}", {"definition": {
        "schema": 2, "pages": [{"title": "T", "parts": [{"type": "table", "source": {
            "kind": "fields", "rows": [{"field": "inspection.depth_fr"}]}}]}]},
        "row_version": 0}, format="json")
    edit(admin, item, fields=[TYRES["fields"][0]])             # depth_fr is removed
    before = FormVersion.objects.count()
    out = push_preview(admin, item)
    assert out["blocked"] is True
    problem = out["forms"][0]["problems"][0]
    assert problem["form"] == "pdi" and "depth_fr" in problem["message"]
    r = push(admin, item)
    assert r.status_code == 409 and r.json()["code"] == "PUSH_BLOCKED"
    assert r.json()["forms"][0]["problems"][0]["code"] == "UNKNOWN_FIELD"
    assert FormVersion.objects.count() == before                           # no new draft
    assert not AuditLog.objects.filter(action="library.push").exists()


def test_a_key_check_pointing_at_a_removed_field_blocks_the_push(admin, make_form, tree):
    item = lib_section(admin)
    f, v, page, _ = new_form(make_form, tree, "pdi")
    add_linked_section(admin, page, item)
    admin.post(f"/api/v1/form-versions/{v}/checks", {
        "rule": {"!!": [{"var": "inspection.depth_fr"}]}, "message": "needs FR",
        "fields": ["depth_fr"]}, format="json")
    edit(admin, item, fields=[TYRES["fields"][0]])
    out = push_preview(admin, item)
    assert out["blocked"] is True and any(
        p["code"] == "UNKNOWN_FIELD" for p in out["forms"][0]["problems"])
    assert f


def test_the_push_is_all_or_nothing_even_when_it_fails_half_way(admin, make_form, tree,
                                                                  monkeypatch):
    from apps.forms import library

    item = lib_field(admin)
    a, va = linked_form(admin, make_form, tree, "pdi", item)
    b, vb = linked_form(admin, make_form, tree, "ev", item)
    edit(admin, item, label="Tread depth")
    real = library.accept_update
    calls = []

    def flaky(actor, obj):
        calls.append(obj.pk)
        if len(calls) == 2:
            raise RuntimeError("boom")
        return real(actor, obj)

    monkeypatch.setattr(library, "accept_update", flaky)
    with pytest.raises(RuntimeError):
        push(admin, item)
    monkeypatch.undo()
    assert find(tree(va), "tyre_depth")["label"] == "Tyre depth"            # first form rolled back
    assert find(tree(vb), "tyre_depth")["label"] == "Tyre depth"
    assert a and b


def test_publishing_automatically_needs_confirmation_and_makes_every_form_live(
        admin, make_form, tree):
    item = lib_field(admin)
    a, va = linked_form(admin, make_form, tree, "pdi", item)
    b, vb = linked_form(admin, make_form, tree, "ev", item, publish_it=True)
    edit(admin, item, label="Tread depth")
    refused = push(admin, item, publish=True)
    assert refused.status_code == 400 and refused.json()["code"] == "CONFIRM_REQUIRED"
    assert find(tree(va), "tyre_depth")["label"] == "Tyre depth"
    ok = push(admin, item, publish=True, confirm=True)
    assert ok.status_code == 200
    for form in (a, b):
        live = FormVersion.objects.filter(form_id=form["id"], status="published").order_by(
            "-number").first()
        assert live and find(tree(live.id), "tyre_depth")["label"] == "Tread depth"
        assert not FormVersion.objects.filter(form_id=form["id"], status="draft").exists()
    assert "published" in AuditLog.objects.get(action="library.push").summary


def test_a_push_from_an_old_revision_is_refused(admin, make_form, tree):
    item = lib_field(admin)
    linked_form(admin, make_form, tree, "pdi", item)
    edit(admin, item, label="Tread depth")
    r = admin.post(f"/api/v1/library/{item['id']}/push", {"revision": 1}, format="json")
    assert r.status_code == 409 and r.json()["code"] == "STALE_LIBRARY_ITEM"


def test_a_section_push_reports_added_removed_and_reordered_fields(admin, make_form, tree):
    item = lib_section(admin)
    f, v, page, _ = new_form(make_form, tree, "pdi")
    add_linked_section(admin, page, item)
    edit(admin, item, title="Tyre set", fields=[
        TYRES["fields"][1], {"key": "depth_rl", "label": "RL", "type": "number",
                             "config": {"unit": "mm"}}])
    changes = push_preview(admin, item)["forms"][0]["changes"]
    kinds = {(c["target"], c["setting"]) for c in changes}
    assert ("depth_fl", "removed") in kinds and ("depth_rl", "added") in kinds
    assert ("depth_fr", "order") in kinds and ("section Tyres", "title") in kinds
    assert f and v


def test_nothing_in_the_library_belongs_to_anyone_but_admin(admin, api_as, make_form, tree):
    item = lib_field(admin)
    linked_form(admin, make_form, tree, "pdi", item)
    ops, _ = api_as(Role.OPS)
    assert ops.get("/api/v1/library").status_code == 200                    # read only
    assert ops.post(f"/api/v1/library/{item['id']}/push-preview").status_code == 403
    assert ops.post(f"/api/v1/library/{item['id']}/push", {}, format="json").status_code == 403
    assert ops.post("/api/v1/library", {"kind": "field", "key": "x1", "definition": DEPTH},
                    format="json").status_code == 403
    grant = admin.put("/api/v1/roles/ops/permissions", {"permissions": {"library.edit": "all",
                      "library.view": "all"}}, format="json")
    assert grant.status_code == 400 and grant.json()["code"] == "NOT_GRANTABLE"


def test_the_migration_gives_old_items_a_history_row_and_removes_old_grants():
    import importlib

    from django.apps import apps as real_apps

    from apps.accounts.models import RolePermission

    item = LibraryItem.objects.create(kind="field", key="old_one", name="Old", definition=DEPTH,
                                      revision=3)
    RolePermission.objects.create(role="ops", permission="library.edit", scope="all")
    migration = importlib.import_module("apps.forms.migrations.0014_library_history_and_admin_only")
    migration.backfill(real_apps, None)
    migration.backfill(real_apps, None)                                      # twice is harmless
    assert list(LibraryRevision.objects.filter(item=item).values_list("revision", flat=True)) == [3]
    assert not RolePermission.objects.filter(permission="library.edit").exists()


# ---------------------------------------------------------------- copy and import as new

def full_form(admin, make_form, tree, publish_it=True):
    item = lib_field(admin)
    f, v, page, sec = new_form(make_form, tree, "pdi")
    add_linked_field(admin, sec, item)
    admin.patch(f"/api/v1/form-versions/{v}/settings", {"use_end": False}, format="json")
    admin.post(f"/api/v1/form-versions/{v}/checks", {"rule": {"!!": [{"var": "inspection.tyre_depth"}]},
               "message": "depth", "fields": ["tyre_depth"]}, format="json")
    if publish_it:
        publish(admin, v)
    return f, v, item


def test_duplicate_makes_a_new_draft_with_links_checks_switches_and_template(
        admin, make_form, tree):
    f, v, item = full_form(admin, make_form, tree)
    t = admin.post("/api/v1/pdf-templates", {"form": f["id"]}, format="json").json()
    admin.patch(f"/api/v1/pdf-template-versions/{t['versions'][0]['id']}", {"definition": {
        "type_code": "PDI", "blocks": []}, "row_version": 0}, format="json")
    r = admin.post(f"/api/v1/forms/{f['id']}/duplicate", {"key": "pdi_copy", "name": "PDI copy"},
                   format="json")
    assert r.status_code == 201, r.content
    copy = Form.objects.get(key="pdi_copy")
    assert copy.name == "PDI copy" and copy.type == "custom" and copy.inspection_type == "pdi_copy"
    version = copy.versions.get()
    assert version.status == "draft" and (version.use_start, version.use_end) == (True, False)
    field = find(tree(version.id), "tyre_depth")
    assert field["library"]["item"] == item["id"] and field["library"]["revision"] == 1
    assert len(tree(version.id)["checks"]) == 1
    assert copy.pdf_template.versions.count() == 1
    assert LibraryItem.objects.count() == 1                               # nothing duplicated
    assert AuditLog.objects.filter(action="form.duplicate").exists()
    # and a later push reaches the copy as well
    edit(admin, item, label="Tread depth")
    forms = {x["form"] for x in push_preview(admin, item)["forms"]}
    assert forms == {"pdi", "pdi_copy"}


@pytest.mark.parametrize("body,code,status", [
    ({}, "INVALID_BUNDLE", 400), ({"key": "Bad Key", "name": "X"}, "INVALID_BUNDLE", 400),
    ({"key": "okay", "name": " "}, "INVALID_BUNDLE", 400),
    ({"key": "pdi", "name": "Same key"}, "KEY_TAKEN", 409)])
def test_duplicate_needs_a_fresh_key_and_a_name(admin, make_form, tree, body, code, status):
    f, _, _ = full_form(admin, make_form, tree)
    r = admin.post(f"/api/v1/forms/{f['id']}/duplicate", body, format="json")
    assert r.status_code == status and r.json()["code"] == code


def test_system_forms_cannot_be_duplicated_and_only_forms_editors_may(admin, api_as):
    start = Form.objects.get(type="start")
    r = admin.post(f"/api/v1/forms/{start.id}/duplicate", {"key": "s2", "name": "S2"},
                   format="json")
    assert r.status_code == 400 and r.json()["code"] == "NOT_DUPLICABLE"
    ops, _ = api_as(Role.OPS)
    assert ops.post(f"/api/v1/forms/{start.id}/duplicate", {}, format="json").status_code == 403


def test_importing_a_bundle_as_a_new_form_never_changes_the_library(admin, make_form, tree):
    f, v, item = full_form(admin, make_form, tree)
    bundle = admin.get(f"/api/v1/promote/export?version={v}").json()
    LibraryItem.objects.filter(pk=item["id"]).update(
        definition={**DEPTH, "label": "Edited here since"})
    r = admin.post("/api/v1/promote/import?as_new_key=pdi_two&as_new_name=PDI%20two", bundle,
                   format="json")
    assert r.status_code == 201, r.content
    assert any("already exists here with different content" in n for n in r.json()["notes"])
    assert LibraryItem.objects.get(pk=item["id"]).definition["label"] == "Edited here since"
    assert Form.objects.filter(key="pdi_two").exists() and Form.objects.filter(key="pdi").exists()


def test_a_section_definition_checks_its_access_and_visible_flag(admin):
    for extra, code in (({"access": {"boss": {}}}, "INVALID_ACCESS"),
                        ({"visible": "yes"}, "INVALID_DEFINITION")):
        r = admin.post("/api/v1/library", {"kind": "section", "key": "tyres",
                                           "definition": {**TYRES, **extra}}, format="json")
        assert r.status_code == 400 and r.json()["code"] == code


def test_a_save_may_rename_the_item_at_the_same_time(admin):
    item = lib_field(admin)
    r = admin.patch(f"/api/v1/library/{item['id']}", {
        "definition": {**item["definition"], "label": "Tread"}, "revision": 1,
        "name": "Tread depth item"}, format="json")
    assert r.status_code == 200 and r.json()["name"] == "Tread depth item"
    assert LibraryRevision.objects.get(item_id=item["id"], revision=2).name == "Tread depth item"


def test_the_list_says_how_many_forms_use_each_item(admin, make_form, tree):
    item = lib_field(admin)
    linked_form(admin, make_form, tree, "pdi", item)
    linked_form(admin, make_form, tree, "ev", item)
    rows = admin.get("/api/v1/library").json()["results"]
    assert rows[0]["used_in"] == 2


def test_the_push_preview_warns_about_integrations_that_use_a_removed_field(
        admin, make_form, tree):
    from apps.integrations.models import Integration

    item = lib_section(admin)
    f, v, page, _ = new_form(make_form, tree, "pdi")
    add_linked_section(admin, page, item)
    publish(admin, v)
    Integration.objects.create(
        form_id=f["id"], name="CRM", event="pdf.ready", url="https://hooks.example.com/x",
        body_mode="custom", body={"fl": "{{inspection.depth_fl}}", "fr": "{{inspection.depth_fr}}"})
    edit(admin, item, fields=[TYRES["fields"][1]])           # depth_fl leaves the section
    form = push_preview(admin, item)["forms"][0]
    assert [(w["name"], w["keys"]) for w in form["warnings"]] == [("CRM", ["inspection.depth_fl"])]
    assert push(admin, item).status_code == 200


def test_a_push_that_keeps_every_field_warns_about_nothing(admin, make_form, tree):
    item = lib_field(admin)
    linked_form(admin, make_form, tree, "pdi", item, publish_it=True)
    edit(admin, item, label="Tread depth")
    assert push_preview(admin, item)["forms"][0]["warnings"] == []
