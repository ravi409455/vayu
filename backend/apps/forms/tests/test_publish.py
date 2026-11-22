"""Publishing a draft: validation, row-version guard, audit, immutability."""
import threading

import pytest
from django.db import connection

from apps.accounts.models import AuditLog, Role
from apps.forms.models import Field, FormVersion

pytestmark = pytest.mark.django_db
V = lambda k: {"var": k}  # noqa: E731


def publish_api(client, version_id, row_version=None):
    if row_version is None:
        row_version = client.get(f"/api/v1/form-versions/{version_id}").json()["row_version"]
    return client.post(f"/api/v1/form-versions/{version_id}/publish",
                       {"row_version": row_version}, format="json")


@pytest.fixture
def form_v(make_form, tree):
    form = make_form()
    v = form["draft_version"]["id"]
    return form, v, tree(v)["pages"][0]["sections"][0]["id"]


def test_publish_freezes_the_version(admin, form_v, tree):
    form, v, _ = form_v
    r = publish_api(admin, v)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "published" and body["warnings"] == []
    t = tree(v)
    assert t["status"] == "published" and t["published_at"] is not None
    listed = admin.get(f"/api/v1/forms/{form['id']}").json()
    assert listed["published_version"] == {"id": v, "number": 1}
    assert listed["draft_version"] is None


def test_published_pointer_moves_and_old_versions_stay_readable(admin, form_v, tree, add_field):
    form, v1, s = form_v
    add_field(s, "paint")
    publish_api(admin, v1)
    v2 = admin.post(f"/api/v1/forms/{form['id']}/drafts").json()["id"]
    s2 = tree(v2)["pages"][0]["sections"][0]["id"]
    add_field(s2, "gloss")
    publish_api(admin, v2)
    listed = admin.get(f"/api/v1/forms/{form['id']}").json()
    assert listed["published_version"]["number"] == 2
    keys1 = {f["key"] for p in tree(v1)["pages"] for sec in p["sections"] for f in sec["fields"]}
    keys2 = {f["key"] for p in tree(v2)["pages"] for sec in p["sections"] for f in sec["fields"]}
    assert "gloss" not in keys1 and "gloss" in keys2
    assert tree(v1)["status"] == "published"


def test_only_admin_publishes(api_as, admin, form_v):
    _, v, _ = form_v
    for role in (Role.OPS, Role.EXPERT):
        client, _ = api_as(role)
        assert client.post(f"/api/v1/form-versions/{v}/publish", {"row_version": 0},
                           format="json").status_code == 403


def test_publish_is_audited(admin, form_v):
    _, v, _ = form_v
    publish_api(admin, v)
    row = AuditLog.objects.get(action="form.publish")
    assert "v1" in row.summary and row.target_id == str(v)


def test_already_published_is_409(admin, form_v):
    _, v, _ = form_v
    publish_api(admin, v)
    r = admin.post(f"/api/v1/form-versions/{v}/publish", {"row_version": 99}, format="json")
    assert r.status_code == 409 and r.json()["code"] == "VERSION_PUBLISHED"


def test_row_version_is_required_and_must_match(admin, form_v, add_field):
    _, v, s = form_v
    assert admin.post(f"/api/v1/form-versions/{v}/publish", {}, format="json").status_code == 400
    seen = admin.get(f"/api/v1/form-versions/{v}").json()["row_version"]
    add_field(s, "paint")  # somebody else changes the draft after we looked at it
    r = publish_api(admin, v, row_version=seen)
    assert r.status_code == 409 and r.json()["code"] == "STALE_DRAFT"
    assert FormVersion.objects.get(pk=v).status == "draft"
    assert publish_api(admin, v).status_code == 200  # with a fresh row_version it works


@pytest.mark.parametrize("mutate", [
    lambda a, ctx: a.post(f"/api/v1/form-versions/{ctx['v']}/pages", {"title": "P"},
                          format="json"),
    lambda a, ctx: a.patch(f"/api/v1/pages/{ctx['page']}", {"title": "Q"}, format="json"),
    lambda a, ctx: a.post(f"/api/v1/pages/{ctx['page']}/sections", {"title": "S"}, format="json"),
    lambda a, ctx: a.patch(f"/api/v1/sections/{ctx['s']}", {"title": "S2"}, format="json"),
    lambda a, ctx: a.post(f"/api/v1/sections/{ctx['s']}/fields",
                          {"key": "newf", "label": "N", "type": "short_text"}, format="json"),
    lambda a, ctx: a.patch(f"/api/v1/fields/{ctx['f']}", {"label": "L2"}, format="json"),
    lambda a, ctx: a.delete(f"/api/v1/fields/{ctx['f']}"),
    lambda a, ctx: a.post(f"/api/v1/form-versions/{ctx['v']}/checks",
                          {"rule": {"!": [V("inspection.chassis_no")]}, "message": "m",
                           "fields": ["chassis_no"]}, format="json"),
], ids=["page+", "page~", "section+", "section~", "field+", "field~", "field-", "check+"])
def test_every_draft_change_bumps_row_version(admin, form_v, tree, add_field, mutate):
    _, v, s = form_v
    f = add_field(s, "paint").json()
    page = tree(v)["pages"][0]["id"]
    before = tree(v)["row_version"]
    r = mutate(admin, {"v": v, "page": page, "s": s, "f": f["id"]})
    assert r.status_code < 300, r.content
    assert tree(v)["row_version"] > before


def test_blocked_by_validation_issues(admin, form_v, add_field):
    _, v, s = form_v
    add_field(s, "later", show_if={"==": [V("inspection.ghost"), 1]})
    r = publish_api(admin, v)
    assert r.status_code == 400 and r.json()["code"] == "PUBLISH_BLOCKED"
    issues = {(i["path"], i["code"]) for i in r.json()["issues"]}
    assert ("fields.later.show_if", "UNKNOWN_FIELD") in issues
    assert FormVersion.objects.get(pk=v).status == "draft"


def test_blocked_when_a_system_field_is_missing(admin, make_form, tree):
    form = make_form(key="booking", kind="booking")
    v = form["draft_version"]["id"]
    Field.objects.filter(version_id=v, key="customer_phone").delete()  # bypasses model guards
    r = publish_api(admin, v)
    assert r.status_code == 400 and r.json()["code"] == "PUBLISH_BLOCKED"
    assert any(i["code"] == "MISSING_SYSTEM_FIELD" and "customer_phone" in i["message"]
               for i in r.json()["issues"])


def test_blocked_when_a_system_field_is_hidden(admin, make_form):
    form = make_form(key="booking", kind="booking")
    v = form["draft_version"]["id"]
    Field.objects.filter(version_id=v, key="booking_id").update(visible=False)
    r = publish_api(admin, v)
    assert r.status_code == 400
    assert any(i["code"] == "SYSTEM_FIELD_HIDDEN" for i in r.json()["issues"])


def test_pending_library_update_does_not_block(admin, form_v, tree):
    _, v, s = form_v
    d = {"key": "tyre_depth", "label": "Depth", "type": "number", "config": {}}
    item = admin.post("/api/v1/library", {"kind": "field", "key": "tyre_depth", "definition": d},
                      format="json").json()
    admin.post(f"/api/v1/sections/{s}/fields/from-library", {"library_item": item["id"]},
               format="json")
    admin.patch(f"/api/v1/library/{item['id']}", {"definition": {**d, "label": "Tread"}},
                format="json")
    assert publish_api(admin, v).status_code == 200


def test_published_version_is_immutable_via_the_api(admin, form_v):
    _, v, s = form_v
    publish_api(admin, v)
    r = admin.post(f"/api/v1/sections/{s}/fields",
                   {"key": "nope", "label": "N", "type": "short_text"}, format="json")
    assert r.status_code == 409 and r.json()["code"] == "VERSION_PUBLISHED"


@pytest.mark.django_db(transaction=True)
def test_concurrent_publish_exactly_one_wins(admin, make_form, tree):
    form = make_form()
    v = form["draft_version"]["id"]
    rv = tree(v)["row_version"]
    results: list[int] = []
    barrier = threading.Barrier(2)

    def go():
        try:
            from rest_framework.test import APIClient

            from apps.accounts.models import User

            client = APIClient()
            client.force_authenticate(user=User.objects.filter(role=Role.ADMIN).first())
            barrier.wait(timeout=5)
            results.append(client.post(f"/api/v1/form-versions/{v}/publish",
                                       {"row_version": rv}, format="json").status_code)
        finally:
            connection.close()

    threads = [threading.Thread(target=go) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
    assert sorted(results) == [200, 409]
    assert FormVersion.objects.get(pk=v).status == "published"
