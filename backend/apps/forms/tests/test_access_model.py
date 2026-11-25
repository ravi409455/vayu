"""Field-level access (role x stage -> hidden/view/edit) and the booking-type -> form link."""
import pytest
from django.core.management import call_command

from apps.forms.access import (
    LEVELS,
    ROLES,
    STAGES,
    levels_by_stage,
    levels_for,
    resolve,
    validate_access,
)

pytestmark = pytest.mark.django_db

GOOD = {"expert": {"in_progress": "edit", "submitted": "view"}, "ops": {"submitted": "edit"}}


def test_constants():
    assert ROLES == ("expert", "ops", "admin") and LEVELS == ("hidden", "view", "edit")
    assert STAGES == ("draft", "assigned", "in_progress", "submitted", "completed", "cancelled")


@pytest.mark.parametrize("value", [{}, GOOD, {"admin": {"draft": "hidden"}}])
def test_valid_access(value):
    validate_access(value)


@pytest.mark.parametrize("value", [
    [], "edit", {"boss": {"draft": "edit"}}, {"expert": {"limbo": "edit"}},
    {"expert": {"draft": "write"}}, {"expert": "edit"}, {"expert": {"draft": True}},
])
def test_invalid_access(value):
    with pytest.raises(ValueError):
        validate_access(value)


def test_resolve_most_specific_layer_wins_and_falls_through():
    field: dict = {"expert": {"draft": "hidden"}}
    section: dict = {"expert": {"draft": "view", "assigned": "view"}}
    page: dict = {}
    assert resolve("expert", "draft", field, section, page) == "hidden"
    assert resolve("expert", "assigned", field, section, page) == "view"   # falls to section
    assert resolve("expert", "submitted", field, section, page) is None    # nothing defined
    assert resolve("ops", "draft", field, section, page) is None


@pytest.fixture
def section(make_form, tree):
    return tree(make_form()["draft_version"]["id"])["pages"][0]["sections"][0]["id"]


def test_access_is_stored_on_pages_sections_and_fields(admin, make_form, tree, add_field):
    v = make_form()["draft_version"]["id"]
    t: dict = tree(v)
    page, sec = t["pages"][0], t["pages"][0]["sections"][0]
    assert admin.patch(f"/api/v1/pages/{page['id']}", {"access": GOOD}, format="json").status_code == 200
    assert admin.patch(f"/api/v1/sections/{sec['id']}", {"access": GOOD}, format="json").status_code == 200
    f = add_field(sec["id"], "paint", access=GOOD)
    assert f.status_code == 201 and f.json()["access"] == GOOD
    t = tree(v)
    assert t["pages"][0]["access"] == GOOD and t["pages"][0]["sections"][0]["access"] == GOOD


def test_bad_access_is_rejected_everywhere(admin, make_form, tree, add_field):
    v = make_form()["draft_version"]["id"]
    t = tree(v)
    page, sec = t["pages"][0], t["pages"][0]["sections"][0]
    bad = {"boss": {"draft": "edit"}}
    for r in (admin.patch(f"/api/v1/pages/{page['id']}", {"access": bad}, format="json"),
              admin.patch(f"/api/v1/sections/{sec['id']}", {"access": bad}, format="json"),
              add_field(sec["id"], "paint", access=bad)):
        assert r.status_code == 400 and r.json()["code"] == "INVALID_ACCESS"


def test_access_defaults_to_empty_and_survives_new_drafts(admin, make_form, tree, add_field):
    form = make_form()
    v = form["draft_version"]["id"]
    s = tree(v)["pages"][0]["sections"][0]["id"]
    assert add_field(s, "plain").json()["access"] == {}
    add_field(s, "gated", access=GOOD)
    from apps.forms.tests.conftest import publish

    publish(v)
    v2 = admin.post(f"/api/v1/forms/{form['id']}/drafts").json()["id"]
    keys = {f["key"]: f["access"] for p in tree(v2)["pages"] for sec in p["sections"]
            for f in sec["fields"]}
    assert keys["gated"] == GOOD and keys["plain"] == {}


def test_library_definitions_carry_access_and_linked_fields_keep_their_own(admin, make_form, tree):
    v = make_form()["draft_version"]["id"]
    s = tree(v)["pages"][0]["sections"][0]["id"]
    d = {"key": "tyre_depth", "label": "Depth", "type": "number", "config": {}, "access": GOOD}
    item = admin.post("/api/v1/library", {"kind": "field", "key": "tyre_depth", "definition": d},
                      format="json").json()
    f = admin.post(f"/api/v1/sections/{s}/fields/from-library", {"library_item": item["id"]},
                   format="json").json()
    assert f["access"] == GOOD
    mine = {"ops": {"draft": "view"}}
    assert admin.patch(f"/api/v1/fields/{f['id']}", {"access": mine}, format="json").status_code == 200
    admin.patch(f"/api/v1/library/{item['id']}", {"definition": {**d, "label": "Tread"},
                                                  "revision": 1}, format="json")
    admin.post(f"/api/v1/fields/{f['id']}/accept-update")
    g = [x for x in tree(v)["pages"][0]["sections"][0]["fields"] if x["key"] == "tyre_depth"][0]
    assert g["label"] == "Tread" and g["access"] == GOOD  # the library owns the access too
    bad = {**d, "key": "other_one", "access": {"boss": {}}}
    r = admin.post("/api/v1/library", {"kind": "field", "key": "other_one", "definition": bad},
                   format="json")
    assert r.status_code == 400 and r.json()["code"] == "INVALID_ACCESS"


# ---------------------------------------------------------------- booking type -> inspection form

@pytest.fixture
def lists():
    call_command("seed_master_lists")


def test_a_new_form_is_tied_to_the_booking_type_named_by_its_key(admin):
    r = admin.post("/api/v1/forms", {"key": "pdi", "name": "PDI"}, format="json")
    assert r.status_code == 201 and r.json()["inspection_type"] == "pdi"
    assert r.json()["type"] == "custom"


def test_the_type_cannot_be_chosen_or_changed(admin):
    r = admin.post("/api/v1/forms", {"key": "scratch", "name": "S", "inspection_type": "other"},
                   format="json")
    assert r.json()["inspection_type"] == "scratch"                   # always the form's key
    f = r.json()
    admin.patch(f"/api/v1/forms/{f['id']}", {"inspection_type": "used_car"}, format="json")
    assert admin.get(f"/api/v1/forms/{f['id']}").json()["inspection_type"] == "scratch"


@pytest.mark.parametrize("ftype", ["booking", "start", "end"])
def test_only_custom_forms_can_be_created(admin, ftype):
    r = admin.post("/api/v1/forms", {"key": "x_form", "type": ftype, "name": "X"}, format="json")
    assert r.status_code == 400


def test_levels_by_stage_matches_levels_for_and_a_draft_is_never_cached(admin, make_form, tree,
                                                                         add_field):
    from apps.forms.models import Field, FormVersion

    v = make_form()["draft_version"]["id"]
    add_field(tree(v)["pages"][0]["sections"][0]["id"], key="odo",
              access={"expert": {"in_progress": "hidden"}})
    draft = FormVersion.objects.select_related("form").get(pk=v)
    assert levels_by_stage(draft, "expert") == {s: levels_for(draft, "expert", s) for s in STAGES}
    assert levels_by_stage(draft, "expert")["in_progress"]["odo"] == "hidden"
    Field.objects.filter(key="odo").update(access={})            # a draft may change any time
    assert levels_by_stage(draft, "expert")["in_progress"]["odo"] == "edit"
