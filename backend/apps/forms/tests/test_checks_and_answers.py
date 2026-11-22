"""Cross-field checks (CRUD) and full server-side validation of a submission's answers."""
import pytest

from apps.forms.rules import validate_answers
from apps.forms.models import FormVersion

from .conftest import publish

pytestmark = pytest.mark.django_db
V = lambda k: {"var": k}  # noqa: E731
MFG = {"rule": {"<=": [V("inspection.mfg"), V("_today")]}, "message": "Not in the future",
       "fields": ["mfg"]}


@pytest.fixture
def form_v(make_form, tree):
    form = make_form()
    v = form["draft_version"]["id"]
    return form, v, tree(v)["pages"][0]["sections"][0]["id"]


def test_checks_crud_and_tree(form_v, add_field, admin, tree):
    _, v, s = form_v
    add_field(s, "mfg", type="date")
    c = admin.post(f"/api/v1/form-versions/{v}/checks", MFG, format="json")
    assert c.status_code == 201
    cid = c.json()["id"]
    assert admin.patch(f"/api/v1/checks/{cid}", {"message": "No future dates"},
                       format="json").status_code == 200
    assert tree(v)["checks"][0]["message"] == "No future dates"
    assert admin.delete(f"/api/v1/checks/{cid}").status_code == 204


@pytest.mark.parametrize("body,code", [
    ({**MFG, "rule": {"missing": ["x"]}}, "INVALID_RULE"),
    ({**MFG, "fields": []}, "INVALID_CHECK"),
    ({**MFG, "message": ""}, "INVALID_CHECK"),
])
def test_invalid_checks_rejected(form_v, add_field, admin, body, code):
    _, v, s = form_v
    add_field(s, "mfg", type="date")
    r = admin.post(f"/api/v1/form-versions/{v}/checks", body, format="json")
    assert r.status_code == 400 and r.json()["code"] == code


def test_checks_are_locked_when_published_and_copied_to_new_drafts(form_v, add_field, admin, tree):
    form, v, s = form_v
    add_field(s, "mfg", type="date")
    cid = admin.post(f"/api/v1/form-versions/{v}/checks", MFG, format="json").json()["id"]
    publish(v)
    assert admin.patch(f"/api/v1/checks/{cid}", {"message": "x"},
                       format="json").json()["code"] == "VERSION_PUBLISHED"
    v2 = admin.post(f"/api/v1/forms/{form['id']}/drafts").json()["id"]
    assert [c["message"] for c in tree(v2)["checks"]] == ["Not in the future"]


def test_check_referencing_unknown_field_is_reported(form_v, add_field, admin):
    _, v, s = form_v
    add_field(s, "mfg", type="date")
    admin.post(f"/api/v1/form-versions/{v}/checks", {**MFG, "fields": ["ghost"]}, format="json")
    issues = {(i["path"], i["code"]) for i in
              admin.post(f"/api/v1/form-versions/{v}/validate").json()["issues"]}
    assert any(code == "UNKNOWN_FIELD" and path.startswith("checks.") for path, code in issues)


# ---- validate_answers: rules + per-type cleaning, as Phase 4 submissions will use it

def build(form_v, add_field, admin):
    _, v, s = form_v
    add_field(s, "door", type="single_choice", config={"options": [
        {"key": "ok", "label": "Ok"},
        {"key": "dent", "label": "Dent", "is_defect": True, "severity": "major"}]},
        required=True)
    add_field(s, "door_photo", type="photo", config={"max_count": 2},
              required_if={"==": [V("inspection.door"), "dent"]})
    add_field(s, "odo", type="number", config={"min": 0, "max": 999999})
    add_field(s, "mfg", type="date")
    admin.post(f"/api/v1/form-versions/{v}/checks", MFG, format="json")
    return FormVersion.objects.get(pk=v)


def test_valid_answers_are_cleaned(form_v, add_field, admin):
    version = build(form_v, add_field, admin)
    cleaned, errors = validate_answers(version, {"inspection": {
        "chassis_no": " MA3YPKCSKTJ273129 ", "door": "ok", "odo": "45", "mfg": "2026-09-01"}},
        today="2026-10-14")
    assert errors == {}
    assert cleaned["chassis_no"] == "MA3YPKCSKTJ273129" and cleaned["odo"] == 45


def test_required_type_and_check_errors_are_combined(form_v, add_field, admin):
    version = build(form_v, add_field, admin)
    _, errors = validate_answers(version, {"inspection": {
        "chassis_no": "X", "door": "dent", "odo": -5, "mfg": "2027-01-01"}}, today="2026-10-14")
    assert errors == {"door_photo": "required", "odo": "OUT_OF_RANGE", "mfg": "check_failed"}


def test_bad_value_in_a_hidden_field_is_ignored_and_dropped(form_v, add_field, admin):
    version = build(form_v, add_field, admin)
    s = form_v[2]
    add_field(s, "dent_size", type="number", show_if={"==": [V("inspection.door"), "dent"]})
    cleaned, errors = validate_answers(version, {"inspection": {
        "chassis_no": "X", "door": "ok", "dent_size": "not a number"}}, today="2026-10-14")
    assert errors == {}
    assert "dent_size" not in cleaned


def test_bad_value_in_a_visible_optional_field_is_an_error(form_v, add_field, admin):
    version = build(form_v, add_field, admin)
    _, errors = validate_answers(version, {"inspection": {
        "chassis_no": "X", "door": "ok", "door_photo": ["not-a-uuid"]}}, today="2026-10-14")
    assert errors == {"door_photo": "INVALID_MEDIA_ID"}


def test_unknown_answer_keys_are_rejected(form_v, add_field, admin):
    version = build(form_v, add_field, admin)
    _, errors = validate_answers(version, {"inspection": {"chassis_no": "X", "door": "ok",
                                                          "ghost": 1}}, today="2026-10-14")
    assert errors == {"ghost": "UNKNOWN_FIELD"}


def test_answers_to_system_filled_fields_are_rejected(form_v, add_field, admin):
    _, v, s = form_v
    add_field(s, "kc", type="derived",
              config={"rule": {"!!": [V("_defects")]}, "true_label": "Y", "false_label": "N"})
    version = FormVersion.objects.get(pk=v)
    _, errors = validate_answers(version, {"inspection": {"chassis_no": "X", "kc": True}},
                                 today="2026-10-14")
    assert errors == {"kc": "SYSTEM_FILLED"}
