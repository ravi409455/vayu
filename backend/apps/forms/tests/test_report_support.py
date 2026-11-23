"""What the PDF report designer needs from forms: a permanent key per section, a print colour per
choice, and two photo settings (issue photo, photo of a check)."""
import pytest

from apps.forms.fieldtypes import ConfigError, validate_config
from apps.forms.models import Section

from .conftest import publish

pytestmark = pytest.mark.django_db
OK = {"key": "ok", "label": "Ok"}


@pytest.fixture
def form_v(make_form, tree):
    form = make_form()
    v = form["draft_version"]["id"]
    page = tree(v)["pages"][0]
    return form, v, page


def new_section(admin, page_id, title):
    r = admin.post(f"/api/v1/pages/{page_id}/sections", {"title": title}, format="json")
    assert r.status_code == 201, r.json()
    return r.json()


# ---------------------------------------------------------------- section keys

@pytest.mark.parametrize("title,key", [
    ("Driver side", "driver_side"), ("  Glass & mirrors!  ", "glass_mirrors"),
    ("4x4 checks", "s_4x4_checks"), ("!!!", "section"), ("A" * 80, "a" * 55)])
def test_a_section_key_is_made_from_its_title(admin, form_v, title, key):
    _, _, page = form_v
    assert new_section(admin, page["id"], title)["key"] == key


def test_keys_are_unique_in_a_version(admin, form_v):
    _, _, page = form_v
    keys = [new_section(admin, page["id"], "Tyres")["key"] for _ in range(3)]
    assert keys == ["tyres", "tyres_2", "tyres_3"]


def test_renaming_keeps_the_key_and_the_key_cannot_be_set(admin, form_v):
    _, _, page = form_v
    s = new_section(admin, page["id"], "Front")
    r = admin.patch(f"/api/v1/sections/{s['id']}", {"title": "Front of the car", "key": "x"},
                    format="json")
    assert r.status_code == 200 and r.json()["key"] == "front"


def test_a_new_draft_keeps_the_keys(admin, form_v, tree):
    form, v, page = form_v
    new_section(admin, page["id"], "Rear")
    publish(v)
    v2 = admin.post(f"/api/v1/forms/{form['id']}/drafts").json()["id"]
    keys = lambda vid: [s["key"] for p in tree(vid)["pages"] for s in p["sections"]]  # noqa: E731
    assert keys(v2) == keys(v) and "rear" in keys(v2)


def test_the_orm_fills_the_key_too(form_v):
    _, v, page = form_v
    s = Section.objects.create(version_id=v, page_id=page["id"], title="Underbody")
    assert s.key == "underbody"


# ---------------------------------------------------------------- print colour of a choice

def test_a_choice_may_have_a_print_colour():
    validate_config("single_choice", {"options": [
        {**OK, "tone": "ok"}, {"key": "na", "label": "Not available", "tone": "muted"},
        {"key": "dent", "label": "Dent", "is_defect": True, "severity": "major", "tone": "bad"},
        {"key": "x", "label": "Not checked", "tone": "warn"}]})


def test_an_unknown_print_colour_is_refused():
    with pytest.raises(ConfigError, match="tone"):
        validate_config("multi_choice", {"options": [{**OK, "tone": "purple"}]})


# ---------------------------------------------------------------- photo settings

def test_photo_settings_are_checked():
    validate_config("photo", {"issue_photo": True, "photo_of": "door"})
    with pytest.raises(ConfigError, match="issue_photo"):
        validate_config("photo", {"issue_photo": "yes"})
    with pytest.raises(ConfigError, match="photo_of"):
        validate_config("photo", {"photo_of": "Not A Key"})
    with pytest.raises(ConfigError, match="Unknown config"):
        validate_config("video", {"issue_photo": True})


def issues(admin, v):
    r = admin.post(f"/api/v1/form-versions/{v}/validate")
    return {(i["path"], i["code"]) for i in r.json()["issues"]}


def test_photo_of_must_name_a_check_in_the_same_section(admin, form_v, add_field):
    _, v, page = form_v
    s1, s2 = page["sections"][0]["id"], new_section(admin, page["id"], "Other")["id"]
    assert add_field(s1, "door", "single_choice", config={"options": [OK]}).status_code == 201
    assert add_field(s2, "far", "yes_no").status_code == 201
    assert add_field(s1, "door_photo", "photo", config={"photo_of": "door"}).status_code == 201
    add_field(s1, "lost_photo", "photo", config={"photo_of": "nothing"})
    add_field(s1, "far_photo", "photo", config={"photo_of": "far"})
    add_field(s1, "chain_photo", "photo", config={"photo_of": "door_photo"})
    found = issues(admin, v)
    assert ("fields.door_photo.config.photo_of", "UNKNOWN_FIELD") not in found
    for k in ("lost_photo", "far_photo", "chain_photo"):
        assert (f"fields.{k}.config.photo_of", "UNKNOWN_FIELD") in found
