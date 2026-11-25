"""Cross-field checks (CRUD) and full server-side validation of a submission's answers."""
import pytest

from apps.forms.models import FormVersion
from apps.forms.rules import validate_answers

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
    assert errors == {"door_photo": "required", "odo": "OUT_OF_RANGE", "mfg": "Not in the future"}


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


def test_empty_answers_are_skipped_not_errors(form_v, add_field, admin):
    version = build(form_v, add_field, admin)
    cleaned, errors = validate_answers(version, {"inspection": {
        "chassis_no": "X", "door": "ok", "odo": "", "mfg": "  "}}, today="2026-10-14")
    assert errors == {} and "odo" not in cleaned and "mfg" not in cleaned


def test_runtime_oscillation_is_caught_not_looped_forever():
    from apps.forms.rules import FormSpec, evaluate_form

    spec = FormSpec.from_dict({"form": "inspection", "containers": [
        {"id": "p", "kind": "page"}, {"id": "s", "kind": "section", "parent": "p"}], "fields": [
        {"key": "aa", "type": "short_text", "section": "s", "show_if": {"!": [V("inspection.bb")]}},
        {"key": "bb", "type": "short_text", "section": "s", "show_if": {"!": [V("inspection.aa")]}},
    ]})
    with pytest.raises(RuntimeError, match="cycle"):
        evaluate_form(spec, {"inspection": {"aa": "x", "bb": "y"}}, "2026-10-14")


def test_an_unchanged_value_whose_user_left_is_kept_but_rules_still_run(form_v, add_field,
                                                                        admin, make_user):
    """H-07: only an unchanged stored value is let through, and only for archived / inactive."""
    version = build(form_v, add_field, admin)
    add_field(form_v[2], "lead", type="user_picker", config={"role": "ops"})
    gone = make_user("ops", username="gone")
    gone.is_active = False
    gone.save()
    answers = {"chassis_no": "X", "door": "ok", "lead": gone.id}
    _, errors = validate_answers(version, {"inspection": answers}, today="2026-10-14")
    assert errors == {"lead": "INVALID_USER"}                          # a new choice: refused
    cleaned, errors = validate_answers(version, {"inspection": answers}, today="2026-10-14",
                                       kept={"lead": gone.id})
    assert errors == {} and cleaned["lead"] == gone.id
    _, errors = validate_answers(version, {"inspection": {**answers, "door": "dent"}},
                                 today="2026-10-14", kept={"lead": gone.id})
    assert errors == {"door_photo": "required"}                        # rules still run
    _, errors = validate_answers(version, {"inspection": {**answers, "odo": -1}},
                                 today="2026-10-14", kept={"lead": gone.id, "odo": -1})
    assert errors == {"odo": "OUT_OF_RANGE"}                           # other codes never kept


@pytest.mark.parametrize("cfg,value,words", [
    ({"min": 0}, -1, "Must be at least 0."), ({"max": 9}, 10, "Must be at most 9."),
    ({"min": 1, "max": 9}, 10, "Must be between 1 and 9.")])
def test_a_range_message_never_says_none(cfg, value, words):
    """F-007 (the broken message): one end of the range left open."""
    from types import SimpleNamespace

    from apps.forms.fieldtypes import AnswerError, clean_answer

    with pytest.raises(AnswerError) as e:
        clean_answer(SimpleNamespace(type="number", config=cfg, key="odo"), value)
    assert str(e.value) == words


@pytest.mark.parametrize("key,limit", [("chassis_no", 64), ("booking_id", 64), ("note", 200)])
def test_text_copied_into_a_column_is_never_longer_than_it(key, limit):
    """F-120: a named TOO_LONG instead of a database error."""
    from types import SimpleNamespace

    from apps.forms.fieldtypes import AnswerError, clean_answer

    f = SimpleNamespace(type="short_text", config={}, key=key)
    assert clean_answer(f, "x" * limit) == "x" * limit
    with pytest.raises(AnswerError) as e:
        clean_answer(f, "x" * (limit + 1))
    assert e.value.code == "TOO_LONG"


def test_a_file_field_without_its_own_maximum_takes_one():
    """F-010: the same default everywhere (web, Android and the builder read it from here)."""
    from types import SimpleNamespace

    from apps.forms.fieldtypes import DEFAULT_MAX_COUNT, AnswerError, clean_answer

    assert DEFAULT_MAX_COUNT == {"photo": 1, "video": 1, "file": 1}
    f = SimpleNamespace(type="photo", config={}, key="p")
    ids = ["5f0c3c8e-2f4e-4a57-9f9c-0d7b6a1d2e3f", "6f0c3c8e-2f4e-4a57-9f9c-0d7b6a1d2e3f"]
    assert clean_answer(f, ids[:1]) == ids[:1]
    with pytest.raises(AnswerError) as e:
        clean_answer(f, ids)
    assert e.value.code == "TOO_MANY"


def test_the_migration_writes_the_old_default_into_fields_that_relied_on_it(form_v, add_field):
    from importlib import import_module

    from django.apps import apps as django_apps

    from apps.forms.models import Field, LibraryItem

    _, v, s = form_v
    add_field(s, "pics", type="photo")
    add_field(s, "clips", type="video", config={"max_count": 2})
    Field.objects.filter(key="pics").update(config={})
    sec = LibraryItem.objects.create(kind="section", key="sec", name="S", definition={
        "title": "S", "fields": [{"key": "doc", "label": "Doc", "type": "file"},
                                 {"key": "t", "label": "T", "type": "short_text"}]})
    one = LibraryItem.objects.create(kind="field", key="one", name="One", definition={
        "key": "one", "label": "One", "type": "photo", "config": {"max_count": 4}})
    import_module("apps.forms.migrations.0020_explicit_max_count").write_old_default(
        django_apps, None)
    assert Field.objects.get(key="pics").config["max_count"] == 10
    assert Field.objects.get(key="clips").config["max_count"] == 2          # its own, kept
    sec.refresh_from_db()
    one.refresh_from_db()
    assert sec.definition["fields"][0]["config"] == {"max_count": 5}
    assert "config" not in sec.definition["fields"][1]
    assert one.definition["config"] == {"max_count": 4}


def test_every_error_comes_with_the_servers_words(form_v, add_field, admin):
    """F-007: the field's own words, the Admin's check message or the rule's; codes unchanged."""
    version = build(form_v, add_field, admin)
    add_field(form_v[2], "plate", type="short_text",
              config={"pattern": "[A-Z]{2}", "pattern_message": "Two capital letters."})
    words: dict = {}
    _, errors = validate_answers(version, {"inspection": {
        "chassis_no": "X", "door": "dent", "odo": -5, "mfg": "2027-01-01", "plate": "x1"}},
        today="2026-10-14", messages=words)
    assert errors == {"door_photo": "required", "odo": "OUT_OF_RANGE", "mfg": "Not in the future",
                      "plate": "PATTERN_MISMATCH"}
    assert words == {"door_photo": "This is required.", "odo": "Must be between 0 and 999999.",
                     "mfg": "Not in the future", "plate": "Two capital letters."}
    unknown: dict = {}
    validate_answers(version, {"inspection": {"nope": 1}}, today="2026-10-14", messages=unknown)
    assert unknown == {"nope": "Not a field of this form."}
