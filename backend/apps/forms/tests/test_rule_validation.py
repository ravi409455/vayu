"""Design-time checks on rules: syntax at save time, references and cycles at validate time."""
import pytest

from apps.forms.models import MasterList
from apps.forms.rules import rule_syntax_issues

pytestmark = pytest.mark.django_db
V = lambda k: {"var": k}  # noqa: E731


@pytest.mark.parametrize("rule,code", [
    ({"frobnicate": [1]}, "UNKNOWN_OPERATOR"),
    ({"missing": ["inspection.a"]}, "BANNED_OPERATOR"),
    ({"missing_some": [1, ["inspection.a"]]}, "BANNED_OPERATOR"),
    ({"and": []}, "EMPTY_OPERATOR"),
    ({"or": []}, "EMPTY_OPERATOR"),
    ({"in": [V("inspection.a"), [V("inspection.b")]]}, "NESTED_IN_ARRAY"),
    ({"==": [1, 2], "!=": [1, 2]}, "INVALID_RULE"),  # one operator per object
    ([1, 2], "INVALID_RULE"),
    ({"var": 5}, "INVALID_RULE"),
])
def test_bad_syntax(rule, code):
    issues = rule_syntax_issues(rule, "fields.x.show_if")
    assert [i.code for i in issues] == [code]
    assert issues[0].path.startswith("fields.x.show_if")


@pytest.mark.parametrize("rule", [
    None,
    {"==": [V("inspection.a"), "x"]},
    {"!": [V("inspection.a")]},
    {"var": ["inspection.a", "default"]},
    {"some": [V("_defects"), {"in": [V(""), ["inspection.a", "inspection.b"]]}]},
    {"reduce": [V("_defects"), {"+": [V("accumulator"), 1]}, 0]},
    {"<=": [V("inspection.mfg"), V("_today")]},
    {"if": [V("inspection.a"), "x", "y"]},
    True,
])
def test_good_syntax(rule):
    assert rule_syntax_issues(rule, "p") == []


def test_nested_path_points_at_the_bad_node():
    rule = {"and": [{"==": [1, 1]}, {"or": [{"bogus": [1]}]}]}
    [issue] = rule_syntax_issues(rule, "fields.x.show_if")
    assert issue.path == "fields.x.show_if.and[1].or[0]"


# ---- API: syntax rejected at save, references/cycles reported by /validate

@pytest.fixture
def form_v(make_form, tree):
    form = make_form()
    v = form["draft_version"]["id"]
    return v, tree(v)["pages"][0]["sections"][0]["id"]


def test_bad_rule_syntax_rejected_at_save(form_v, add_field, admin):
    v, s = form_v
    r = add_field(s, "b", show_if={"missing": ["inspection.a"]})
    assert r.status_code == 400 and r.json()["code"] == "INVALID_RULE"
    f = add_field(s, "c").json()
    r = admin.patch(f"/api/v1/fields/{f['id']}", {"required_if": {"nope": [1]}}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "INVALID_RULE"


def validate(admin, v):
    r = admin.post(f"/api/v1/form-versions/{v}/validate")
    assert r.status_code == 200
    return {(i["path"], i["code"]) for i in r.json()["issues"]}


def test_clean_version_has_no_issues(form_v, add_field, admin):
    v, s = form_v
    add_field(s, "a")
    add_field(s, "b", show_if={"==": [V("inspection.a"), "x"]})
    assert validate(admin, v) == set()


def test_unknown_field_references(form_v, add_field, admin):
    v, s = form_v
    add_field(s, "b", show_if={"==": [V("inspection.nope"), "x"]})
    add_field(s, "c", required_if={"==": [V("booking.fuel_type"), "cng"]})  # no booking form
    add_field(s, "d", show_if={"==": [V("a"), 1]})  # unqualified
    issues = validate(admin, v)
    assert ("fields.b.show_if", "UNKNOWN_FIELD") in issues
    assert ("fields.c.required_if", "UNKNOWN_FIELD") in issues
    assert ("fields.d.show_if", "UNKNOWN_FIELD") in issues


def test_cross_form_reference_to_existing_booking_field(make_form, form_v, add_field, admin, tree):
    booking = make_form(key="booking", kind="booking")
    bs = tree(booking["draft_version"]["id"])["pages"][0]["sections"][0]["id"]
    add_field(bs, "fuel_type", type="single_choice",
              config={"options": [{"key": "cng", "label": "CNG"}]})
    v, s = form_v
    add_field(s, "hydro", type="date", show_if={"==": [V("booking.fuel_type"), "cng"]})
    assert validate(admin, v) == set()


def test_rules_may_not_read_system_filled_fields(form_v, add_field, admin):
    v, s = form_v
    add_field(s, "kc", type="derived",
              config={"rule": {"!!": [V("_defects")]}, "true_label": "Y", "false_label": "N"})
    add_field(s, "b", show_if={"==": [V("inspection.kc"), True]})
    assert ("fields.b.show_if", "SYSTEM_FIELD_IN_RULE") in validate(admin, v)


@pytest.mark.parametrize("a_rule,b_rule", [
    ({"==": [V("inspection.b"), 1]}, {"==": [V("inspection.a"), 1]}),   # a <-> b
    ({"==": [V("inspection.a"), 1]}, None),                             # a -> a
])
def test_visibility_cycles_detected(form_v, add_field, admin, a_rule, b_rule):
    v, s = form_v
    add_field(s, "a", show_if=a_rule)
    add_field(s, "b", show_if=b_rule)
    assert any(code == "CYCLE" for _, code in validate(admin, v))


def test_section_rule_reading_its_own_field_is_a_cycle(form_v, add_field, admin, tree):
    v, s = form_v
    add_field(s, "a")
    admin.patch(f"/api/v1/sections/{s}", {"show_if": {"==": [V("inspection.a"), 1]}},
                format="json")
    assert any(code == "CYCLE" for _, code in validate(admin, v))


def test_defect_choice_shown_by_defects_is_a_cycle(form_v, add_field, admin):
    v, s = form_v
    opts = [{"key": "dent", "label": "Dent", "is_defect": True, "severity": "minor"}]
    add_field(s, "door", type="single_choice", config={"options": opts},
              show_if={"!!": [V("_defects")]})
    assert any(code == "CYCLE" for _, code in validate(admin, v))


def test_validate_reports_config_problems_too(form_v, add_field, admin):
    MasterList.objects.create(key="city", name="City")
    v, s = form_v
    add_field(s, "c", type="master_list", config={"list": "city"})
    MasterList.objects.filter(key="city").delete()  # list removed after the field was added
    assert ("fields.c.config", "INVALID_CONFIG") in validate(admin, v)


def test_derived_rule_is_checked(form_v, add_field, admin):
    v, s = form_v
    add_field(s, "kc", type="derived", config={"rule": {"==": [V("inspection.ghost"), 1]},
                                               "true_label": "Y", "false_label": "N"})
    assert ("fields.kc.config.rule", "UNKNOWN_FIELD") in validate(admin, v)


def test_only_admin_can_validate(api_as, form_v):
    from apps.accounts.models import Role

    v, _ = form_v
    ops, _ = api_as(Role.OPS)
    assert ops.post(f"/api/v1/form-versions/{v}/validate").status_code == 403
