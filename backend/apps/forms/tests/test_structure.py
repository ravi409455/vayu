import pytest

from apps.accounts.models import AuditLog, Role
from apps.forms.models import Field, FormVersion

from .conftest import publish

pytestmark = pytest.mark.django_db

BOOKING_SYSTEM_KEYS = {
    "booking_id", "customer_name", "customer_phone", "address", "city", "inspection_date",
    "inspection_time", "inspection_type", "car_make_model", "lead_owner", "assigned_expert",
}


def field_keys(t):
    return {f["key"] for p in t["pages"] for s in p["sections"] for f in s["fields"]}


def first_section(t):
    return t["pages"][0]["sections"][0]


def test_new_form_gets_a_draft_v1(make_form, tree):
    form = make_form()
    assert form["draft_version"]["number"] == 1
    t = tree(form["draft_version"]["id"])
    assert t["status"] == "draft" and t["number"] == 1

OPS_SYSTEM_KEYS = {"checkin_gps", "checkin_time", "selfie", "taking_payment", "payment_mode",
                   "payment_amount", "payment_screenshot"}


@pytest.mark.parametrize(
    "kind,expected",
    [("booking", BOOKING_SYSTEM_KEYS), ("inspection", {"chassis_no"}),
     ("start", {"checkin_gps", "checkin_time", "selfie"}),
     ("end", {"taking_payment", "payment_mode", "payment_amount", "payment_screenshot"})],
)
def test_system_fields_are_created_per_type(make_form, tree, kind, expected):
    form = make_form(key=f"{kind}_form", kind=kind)
    t = tree(form["draft_version"]["id"])
    system = {f["key"] for p in t["pages"] for s in p["sections"] for f in s["fields"]
              if f["is_system"]}
    assert system == expected


def test_the_three_system_forms_exist_once_and_cannot_be_added(make_form, admin):
    from apps.forms.models import Form

    assert sorted(Form.objects.exclude(type="custom").values_list("type", flat=True)) == [
        "booking", "end", "start"]
    for kind in ("booking", "start", "end"):
        r = admin.post("/api/v1/forms", {"key": f"{kind}2", "type": kind, "name": kind},
                       format="json")
        assert r.status_code == 400
    make_form(key="ppi")  # many custom forms are fine
    make_form(key="ev")


def test_pages_sections_fields_are_ordered(make_form, admin, tree, add_field):
    v = make_form()["draft_version"]["id"]
    p2 = admin.post(f"/api/v1/form-versions/{v}/pages", {"title": "Tyres", "order": 5},
                    format="json").json()
    s = admin.post(f"/api/v1/pages/{p2['id']}/sections", {"title": "Front", "order": 1},
                   format="json").json()
    add_field(s["id"], "depth_fr", order=2)
    add_field(s["id"], "depth_fl", order=1)
    t = tree(v)
    assert [p["title"] for p in t["pages"]][-1] == "Tyres"
    assert [f["key"] for f in t["pages"][-1]["sections"][0]["fields"]] == ["depth_fl", "depth_fr"]


def test_reorder_and_move_field_between_sections_in_draft(make_form, admin, tree, add_field):
    v = make_form()["draft_version"]["id"]
    t = tree(v)
    page_id = t["pages"][0]["id"]
    other = admin.post(f"/api/v1/pages/{page_id}/sections", {"title": "Other", "order": 9},
                       format="json").json()
    f = add_field(first_section(t)["id"], "paint").json()
    r = admin.patch(f"/api/v1/fields/{f['id']}", {"section": other["id"], "order": 3},
                    format="json")
    assert r.status_code == 200
    moved = [s for s in tree(v)["pages"][0]["sections"] if s["id"] == other["id"]][0]
    assert [x["key"] for x in moved["fields"]] == ["paint"]


def test_cannot_move_field_into_another_versions_section(make_form, admin, tree, add_field):
    v1 = make_form("pdi")["draft_version"]["id"]
    v2 = make_form("ppi")["draft_version"]["id"]
    f = add_field(first_section(tree(v1))["id"], "paint").json()
    r = admin.patch(f"/api/v1/fields/{f['id']}", {"section": first_section(tree(v2))["id"]},
                    format="json")
    assert r.status_code == 400


def test_visibility_flags_and_helper_text_are_stored(make_form, admin, tree, add_field):
    v = make_form()["draft_version"]["id"]
    t = tree(v)
    add_field(first_section(t)["id"], "paint", visible=False, helper_text="Check all panels")
    admin.patch(f"/api/v1/pages/{t['pages'][0]['id']}", {"visible": False}, format="json")
    t = tree(v)
    f = [x for x in first_section(t)["fields"] if x["key"] == "paint"][0]
    assert f["visible"] is False and f["helper_text"] == "Check all panels"
    assert t["pages"][0]["visible"] is False


@pytest.mark.parametrize("key", ["1abc", "Abc", "a", "a-b", "a b", "a" * 64, ""])
def test_invalid_field_keys_rejected(make_form, tree, add_field, key):
    v = make_form()["draft_version"]["id"]
    assert add_field(first_section(tree(v))["id"], key).status_code == 400


def test_valid_key_and_duplicate_in_same_version(make_form, tree, add_field):
    s = first_section(tree(make_form()["draft_version"]["id"]))["id"]
    assert add_field(s, "tyre_depth_fl").status_code == 201
    assert add_field(s, "tyre_depth_fl").status_code == 400


def test_key_and_type_are_immutable(make_form, admin, tree, add_field):
    s = first_section(tree(make_form()["draft_version"]["id"]))["id"]
    f = add_field(s, "paint").json()
    r = admin.patch(f"/api/v1/fields/{f['id']}", {"key": "paint2"}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "KEY_IMMUTABLE"
    r = admin.patch(f"/api/v1/fields/{f['id']}", {"type": "number"}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "TYPE_IMMUTABLE"


def test_deleted_key_stays_reserved_for_its_type(make_form, admin, tree, add_field):
    s = first_section(tree(make_form()["draft_version"]["id"]))["id"]
    f = add_field(s, "paint").json()
    assert admin.delete(f"/api/v1/fields/{f['id']}").status_code == 204
    r = add_field(s, "paint", type="number", config={})
    assert r.status_code == 400 and r.json()["code"] == "KEY_RESERVED"
    assert add_field(s, "paint").status_code == 201  # same type is the same field again


def test_key_reservation_is_per_form(make_form, tree, add_field):
    s1 = first_section(tree(make_form("pdi")["draft_version"]["id"]))["id"]
    s2 = first_section(tree(make_form("ppi")["draft_version"]["id"]))["id"]
    add_field(s1, "paint")
    assert add_field(s2, "paint", type="number", config={}).status_code == 201


def test_system_fields_can_be_relabelled_not_removed_or_reconfigured(make_form, admin, tree):
    t = tree(make_form(key="booking", kind="booking")["draft_version"]["id"])
    city = [f for f in first_section(t)["fields"] if f["key"] == "city"][0]
    r = admin.delete(f"/api/v1/fields/{city['id']}")
    assert r.status_code == 400 and r.json()["code"] == "SYSTEM_FIELD"
    assert admin.patch(f"/api/v1/fields/{city['id']}", {"label": "Inspection city"},
                       format="json").status_code == 200
    r = admin.patch(f"/api/v1/fields/{city['id']}", {"config": {"list": "other"}}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "SYSTEM_FIELD"


def test_published_version_is_immutable(make_form, admin, tree, add_field):
    v = make_form()["draft_version"]["id"]
    t = tree(v)
    page, section = t["pages"][0], first_section(t)
    f = add_field(section["id"], "paint").json()
    publish(v)
    calls = [
        admin.post(f"/api/v1/form-versions/{v}/pages", {"title": "x"}, format="json"),
        admin.patch(f"/api/v1/pages/{page['id']}", {"title": "x"}, format="json"),
        admin.delete(f"/api/v1/pages/{page['id']}"),
        admin.post(f"/api/v1/pages/{page['id']}/sections", {"title": "x"}, format="json"),
        admin.patch(f"/api/v1/sections/{section['id']}", {"title": "x"}, format="json"),
        admin.delete(f"/api/v1/sections/{section['id']}"),
        admin.post(f"/api/v1/sections/{section['id']}/fields",
                   {"key": "new_one", "label": "x", "type": "short_text"}, format="json"),
        admin.patch(f"/api/v1/fields/{f['id']}", {"label": "x"}, format="json"),
        admin.delete(f"/api/v1/fields/{f['id']}"),
    ]
    for r in calls:
        assert r.status_code == 409 and r.json()["code"] == "VERSION_PUBLISHED"


def test_published_version_is_immutable_at_the_orm_level_too(make_form, tree, add_field):
    v = make_form()["draft_version"]["id"]
    add_field(first_section(tree(v))["id"], "paint")
    publish(v)
    f = Field.objects.get(version_id=v, key="paint")
    f.label = "tampered"
    with pytest.raises(Exception, match="VERSION_PUBLISHED"):
        f.save()


def test_new_draft_deep_copies_latest_published(make_form, admin, tree, add_field):
    form = make_form()
    v1 = form["draft_version"]["id"]
    add_field(first_section(tree(v1))["id"], "paint", helper_text="h")
    publish(v1)
    r = admin.post(f"/api/v1/forms/{form['id']}/drafts")
    assert r.status_code == 201
    t2 = tree(r.json()["id"])
    assert t2["number"] == 2 and t2["status"] == "draft"
    assert field_keys(t2) == field_keys(tree(v1))
    old_ids = {f["id"] for p in tree(v1)["pages"] for s in p["sections"] for f in s["fields"]}
    new_ids = {f["id"] for p in t2["pages"] for s in p["sections"] for f in s["fields"]}
    assert old_ids.isdisjoint(new_ids)
    assert admin.post(f"/api/v1/forms/{form['id']}/drafts").json()["code"] == "DRAFT_EXISTS"


def test_ops_reads_forms_expert_cannot_and_only_admin_writes(api_as, make_form, tree):
    form = make_form()
    v = form["draft_version"]["id"]
    ops, _ = api_as(Role.OPS)
    assert ops.get(f"/api/v1/form-versions/{v}").status_code == 200
    assert ops.get("/api/v1/forms").status_code == 200
    assert ops.post("/api/v1/forms", {"key": "x", "name": "x"},
                    format="json").status_code == 403
    assert ops.post(f"/api/v1/form-versions/{v}/pages", {"title": "x"},
                    format="json").status_code == 403
    expert, _ = api_as(Role.EXPERT)
    assert expert.get(f"/api/v1/form-versions/{v}").status_code == 403


def test_form_creation_and_draft_creation_are_audited(make_form, admin, tree):
    form = make_form()
    publish(form["draft_version"]["id"])
    admin.post(f"/api/v1/forms/{form['id']}/drafts")
    actions = set(AuditLog.objects.values_list("action", flat=True))
    assert {"form.create", "form.draft_create"} <= actions
    assert FormVersion.objects.filter(form_id=form["id"]).count() == 2


def test_page_or_section_holding_system_fields_cannot_be_deleted(make_form, admin, tree):
    t = tree(make_form(key="booking", kind="booking")["draft_version"]["id"])
    r = admin.delete(f"/api/v1/sections/{first_section(t)['id']}")
    assert r.status_code == 400 and r.json()["code"] == "SYSTEM_FIELD"
    r = admin.delete(f"/api/v1/pages/{t['pages'][0]['id']}")
    assert r.status_code == 400 and r.json()["code"] == "SYSTEM_FIELD"


def test_empty_sections_and_pages_can_be_deleted_in_draft(make_form, admin, tree):
    v = make_form()["draft_version"]["id"]
    p = admin.post(f"/api/v1/form-versions/{v}/pages", {"title": "Extra"}, format="json").json()
    s = admin.post(f"/api/v1/pages/{p['id']}/sections", {"title": "S"}, format="json").json()
    assert admin.delete(f"/api/v1/sections/{s['id']}").status_code == 204
    assert admin.delete(f"/api/v1/pages/{p['id']}").status_code == 204


def test_draft_cannot_be_created_without_a_published_version(make_form, admin):
    form = make_form()
    r = admin.post(f"/api/v1/forms/{form['id']}/drafts")
    assert r.status_code == 409 and r.json()["code"] == "DRAFT_EXISTS"


def test_draft_needs_something_to_copy(make_form, admin):
    from apps.forms.models import FormVersion

    form = make_form()
    FormVersion.objects.filter(form_id=form["id"]).delete()
    r = admin.post(f"/api/v1/forms/{form['id']}/drafts")
    assert r.status_code == 409 and r.json()["code"] == "NOTHING_TO_COPY"
