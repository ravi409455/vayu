"""Form types: booking / start / end are always there once; custom forms are what Admins build."""
import importlib
from unittest import mock

import pytest
from django.db import DatabaseError, IntegrityError

from apps.forms import apps as forms_apps
from apps.forms.models import Field, Form, FormVersion
from apps.forms.services import ensure_system_forms

from .test_promote import V, export, publish, staging, wipe  # noqa: F401

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------- the system forms

def test_ensure_system_forms_is_idempotent_and_recreates_what_is_missing():
    ensure_system_forms()
    assert sorted(Form.objects.exclude(type="custom").values_list("type", flat=True)) == [
        "booking", "end", "start"]
    Form.objects.filter(type="end").delete()
    Form.objects.create(key="end", type="custom", name="Someone took the key")
    ensure_system_forms()
    ensure_system_forms()
    assert Form.objects.get(type="end").key == "end2"            # a free key is found
    assert Form.objects.filter(type="end").count() == 1


def test_the_database_allows_only_one_of_each_system_form():
    with pytest.raises(IntegrityError):
        Form.objects.create(key="another_booking", type="booking", name="B")


def test_the_post_migrate_hook_survives_a_database_that_is_not_ready():
    with mock.patch("apps.forms.services.ensure_system_forms", side_effect=DatabaseError):
        forms_apps._ensure_system_forms(sender=None)           # must not raise


def test_a_form_cannot_be_given_another_type_or_submission_roles_unless_custom(admin):
    start = Form.objects.get(type="start")
    r = admin.patch(f"/api/v1/forms/{start.id}", {"type": "custom"}, format="json")
    assert Form.objects.get(pk=start.id).type == "start"        # read-only: silently ignored
    assert r.status_code == 200
    r = admin.patch(f"/api/v1/forms/{start.id}", {"submission_roles": ["ops"]}, format="json")
    assert r.status_code == 400


def test_the_forms_list_can_be_filtered_by_type(admin, make_form):
    make_form(key="pdi")
    custom = admin.get("/api/v1/forms?type=custom").json()["results"]
    assert [f["key"] for f in custom] == ["pdi"]
    assert {f["type"] for f in admin.get("/api/v1/forms").json()["results"]} == {
        "booking", "start", "end", "custom"}


# ---------------------------------------------------------------- the two switches

def test_a_custom_version_begins_and_ends_with_the_system_forms_by_default(admin, make_form, tree):
    t = tree(make_form(key="pdi")["draft_version"]["id"])
    assert t["use_start"] is True and t["use_end"] is True


def test_the_switches_change_on_a_draft_and_are_frozen_once_published(admin, make_form, tree):
    form = make_form(key="pdi")
    v = form["draft_version"]["id"]
    r = admin.patch(f"/api/v1/form-versions/{v}/settings", {"use_start": False}, format="json")
    assert r.status_code == 200 and r.json()["use_start"] is False and r.json()["use_end"] is True
    t = tree(v)
    assert t["use_start"] is False and t["use_end"] is True
    publish(admin, v)
    r = admin.patch(f"/api/v1/form-versions/{v}/settings", {"use_end": False}, format="json")
    assert r.status_code == 409 and r.json()["code"] == "VERSION_PUBLISHED"
    d = admin.post(f"/api/v1/forms/{form['id']}/drafts").json()["id"]          # copied forward
    assert tree(d)["use_start"] is False and tree(d)["use_end"] is True


@pytest.mark.parametrize("body", [{}, {"use_start": "yes"}, {"other": True}])
def test_bad_switch_values_are_refused(admin, make_form, body):
    v = make_form(key="pdi")["draft_version"]["id"]
    r = admin.patch(f"/api/v1/form-versions/{v}/settings", body, format="json")
    assert r.status_code == 400 and r.json()["code"] == "INVALID_SETTINGS"


def test_only_custom_forms_have_the_switches(admin):
    v = Form.objects.get(type="start").versions.get().id
    r = admin.patch(f"/api/v1/form-versions/{v}/settings", {"use_start": False}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "INVALID_SETTINGS"


def test_the_switches_travel_in_the_promote_bundle(admin, staging):
    d = admin.post(f"/api/v1/forms/{staging['form']['id']}/drafts").json()["id"]
    admin.patch(f"/api/v1/form-versions/{d}/settings", {"use_end": False}, format="json")
    publish(admin, d)
    bundle = export(admin, d)
    assert bundle["version"]["use_start"] is True and bundle["version"]["use_end"] is False
    wipe()
    r = admin.post("/api/v1/promote/import", bundle, format="json")
    assert r.status_code == 201
    v = FormVersion.objects.get(pk=r.json()["draft_version"])
    assert (v.use_start, v.use_end) == (True, False)
    bundle["version"]["use_start"] = "no"
    wipe()
    assert admin.post("/api/v1/promote/import", bundle, format="json").json()["code"] == \
        "INVALID_BUNDLE"


# ---------------------------------------------------------------- publish checks

def test_a_rule_that_needs_the_start_form_blocks_publishing_when_it_is_switched_off(
        admin, make_form, tree, add_field):
    v = make_form(key="pdi")["draft_version"]["id"]
    sec = tree(v)["pages"][0]["sections"][0]["id"]
    add_field(sec, "note", show_if={"==": [V("start.checkin_gps"), None]})
    rv = admin.get(f"/api/v1/form-versions/{v}").json()["row_version"]
    assert admin.post(f"/api/v1/form-versions/{v}/publish", {"row_version": rv},
                      format="json").status_code == 200            # switched on: fine
    d = admin.post(f"/api/v1/forms/{Form.objects.get(key='pdi').id}/drafts").json()["id"]
    admin.patch(f"/api/v1/form-versions/{d}/settings", {"use_start": False}, format="json")
    rv = admin.get(f"/api/v1/form-versions/{d}").json()["row_version"]
    r = admin.post(f"/api/v1/form-versions/{d}/publish", {"row_version": rv}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "PUBLISH_BLOCKED"
    issue = next(i for i in r.json()["issues"] if i["code"] == "FORM_NOT_INCLUDED")
    assert "begin with it" in issue["message"] and issue["ref"] == "start.checkin_gps"
    admin.patch(f"/api/v1/form-versions/{d}/settings", {"use_start": True, "use_end": False},
                format="json")
    sec = tree(d)["pages"][0]["sections"][0]
    field = next(f for f in sec["fields"] if f["key"] == "note")
    admin.patch(f"/api/v1/fields/{field['id']}", {"show_if": {"==": [V("end.taking_payment"),
                                                                         True]}}, format="json")
    r = admin.post(f"/api/v1/form-versions/{d}/publish",
                   {"row_version": admin.get(f"/api/v1/form-versions/{d}").json()["row_version"]},
                   format="json")
    assert any(i["code"] == "FORM_NOT_INCLUDED" and "end with it" in i["message"]
               for i in r.json()["issues"])


def test_a_pdf_row_that_needs_the_end_form_blocks_the_template_when_it_is_switched_off(
        admin, staging):
    d = admin.post(f"/api/v1/forms/{staging['form']['id']}/drafts").json()["id"]
    admin.patch(f"/api/v1/form-versions/{d}/settings", {"use_end": False}, format="json")
    publish(admin, d)
    template = admin.get("/api/v1/pdf-templates").json()[0]
    draft = admin.post(f"/api/v1/pdf-templates/{template['id']}/drafts").json()
    definition = {"type_code": "PDI", "blocks": [{"type": "table", "title": "Pay", "rows": [
        {"label": "Paid", "field": "end.taking_payment"}]}]}
    admin.patch(f"/api/v1/pdf-template-versions/{draft['id']}", {
        "definition": definition, "row_version": draft["row_version"]}, format="json")
    rv = admin.get(f"/api/v1/pdf-template-versions/{draft['id']}").json()["row_version"]
    r = admin.post(f"/api/v1/pdf-template-versions/{draft['id']}/publish", {"row_version": rv},
                   format="json")
    assert r.status_code == 400
    assert "does not include" in r.json()["issues"][0]["message"]
    assert Field.objects.filter(version__form__type="end", key="taking_payment").exists()


# ---------------------------------------------------------------- the booking's pick of a form

def test_the_booking_form_picks_the_type_from_the_published_custom_forms(admin, make_form):
    from apps.forms.fieldtypes import AnswerError, clean_answer

    field = Field.objects.get(version__form__type="booking", key="inspection_type")
    assert field.type == "form_choice"
    with pytest.raises(AnswerError):
        clean_answer(field, "pdi")                                  # no such form yet
    f = make_form(key="pdi")
    with pytest.raises(AnswerError):
        clean_answer(field, "pdi")                                  # created but not published
    publish(admin, f["draft_version"]["id"])
    assert clean_answer(field, "pdi") == "pdi"
    with pytest.raises(AnswerError):
        clean_answer(field, 5)
    Form.objects.filter(key="pdi").update(is_active=False)
    with pytest.raises(AnswerError):
        clean_answer(field, "pdi")                                  # switched off


# ---------------------------------------------------------------- bundles from before form types

def _v1(bundle: dict, kind: str) -> dict:
    """What an older server would have exported."""
    out = {**bundle, "schema": 1, "form": {k: v for k, v in bundle["form"].items() if k != "type"}}
    out["form"]["kind"] = kind
    return out


def test_an_old_inspection_bundle_still_imports_with_its_ops_references_renamed(admin, staging):
    bundle = _v1(export(admin, staging["version"]), "inspection")
    bundle["version"] = {k: v for k, v in bundle["version"].items() if k not in ("use_start",
                                                                                  "use_end")}
    for p in bundle["version"]["pages"]:
        p["slot"] = ""
        for s in p["sections"]:
            for f in s["fields"]:
                if f["key"] == "door":
                    f["show_if"] = {"==": [{"var": ["ops.taking_payment", False]}, True]}
                if f["key"] == "yard_pick":
                    f["required_if"] = {"!!": [V("ops.selfie")]}
    bundle["pdf_template"] = {"definition": {"blocks": [{"type": "table", "rows": [
        {"label": "Pay", "field": "ops.payment_mode"}, {"label": "Door", "field": "door"}]}]}}
    wipe()
    r = admin.post("/api/v1/promote/import", bundle, format="json")
    assert r.status_code == 201, r.content
    v = r.json()["draft_version"]
    door = Field.objects.get(version_id=v, key="door")
    assert door.show_if == {"==": [{"var": ["end.taking_payment", False]}, True]}
    assert Field.objects.get(version_id=v, key="yard_pick").required_if == {
        "!!": [{"var": "start.selfie"}]}
    from apps.reports.models import PdfTemplateVersion

    pdf = PdfTemplateVersion.objects.get(template__form__key="pdi")
    assert pdf.definition["blocks"][0]["rows"][0]["field"] == "end.payment_mode"
    assert pdf.definition["blocks"][0]["rows"][1]["field"] == "door"
    assert Form.objects.get(key="pdi").type == "custom"


def test_an_old_bundle_that_reads_an_unknown_ops_field_is_refused_clearly(admin, staging):
    bundle = _v1(export(admin, staging["version"]), "inspection")
    bundle["version"]["pages"][0]["sections"][0]["fields"][0]["show_if"] = {"!!": [V("ops.mystery")]}
    wipe()
    r = admin.post("/api/v1/promote/import", bundle, format="json")
    assert r.status_code == 400 and r.json()["code"] == "OLD_BUNDLE"
    assert "ops.mystery" in r.json()["detail"]


def test_an_old_check_in_and_wrap_up_bundle_is_refused_with_what_to_do(admin, staging):
    bundle = _v1(export(admin, staging["version"]), "ops")
    wipe()
    r = admin.post("/api/v1/promote/import", bundle, format="json")
    assert r.status_code == 400 and r.json()["code"] == "OLD_BUNDLE"
    assert "start form and an end form" in r.json()["detail"]


def test_an_old_booking_bundle_gets_the_form_pick_for_the_inspection_type(admin):
    from django.core.management import call_command

    call_command("seed_master_lists")
    form = Form.objects.get(type="booking")
    v = form.versions.get().id
    publish(admin, v)
    bundle = export(admin, v)
    for p in bundle["version"]["pages"]:
        for s in p["sections"]:
            for f in s["fields"]:
                if f["key"] == "inspection_type":
                    f["type"], f["config"] = "master_list", {"list": "inspection_type"}
    bundle["master_lists"] += [{"key": "inspection_type", "name": "T", "items": []}]
    old = _v1(bundle, "booking")
    wipe()
    r = admin.post("/api/v1/promote/import", old, format="json")
    assert r.status_code == 201, r.content
    f = Field.objects.get(version_id=r.json()["draft_version"], key="inspection_type")
    assert f.type == "form_choice" and f.config == {}


# ---------------------------------------------------------------- moving old data across

def _migration(name):
    return importlib.import_module(f"apps.forms.migrations.{name}")


def test_ops_references_in_stored_rules_are_renamed_by_which_form_owns_the_key():
    m = _migration("0010_form_type_data")
    owner = {"selfie": "start", "taking_payment": "end"}
    rule = {"and": [{"==": [{"var": "ops.taking_payment"}, True]},
                    {"!!": [{"var": ["ops.selfie", None]}]},
                    {"==": [{"var": "inspection.door"}, "ok"]},
                    {"some": [{"var": "ops.unknown"}, {"==": [{"var": ""}, 1]}]}]}
    assert m.rewrite(rule, owner) == {"and": [
        {"==": [{"var": "end.taking_payment"}, True]},
        {"!!": [{"var": ["start.selfie", None]}]},
        {"==": [{"var": "inspection.door"}, "ok"]},
        {"some": [{"var": "start.unknown"}, {"==": [{"var": ""}, 1]}]}]}
    assert m.rewrite(None, owner) is None
    assert m.rename_in_text("ops.payment_mode", {"payment_mode": "end"}) == "end.payment_mode"
    assert m.rename_in_text("inspection.door", owner) == "inspection.door"
    assert m.rewrite_strings({"rows": [{"field": "ops.selfie"}, "x"]}, owner) == {
        "rows": [{"field": "start.selfie"}, "x"]}
    assert m.free_key(Form, "start") == "start2"
