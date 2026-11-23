"""Publishing a draft: validation, row-version guard, audit, immutability."""
import threading
import time

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
    assert listed["published_version"] == {"id": v, "number": 1, "use_start": True,
                                           "use_end": True}
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


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
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


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_edits_cannot_slip_into_a_version_while_it_is_being_published(make_form, tree):
    """Regression: an edit that read 'draft' just before a publish committed used to land in the
    published version. Draft writes now take the version's row lock first."""
    from apps.forms.models import Section

    form = make_form()
    v = form["draft_version"]["id"]
    section = Section.objects.filter(version_id=v).first()
    locked = threading.Event()
    outcome: dict = {}

    def publisher():
        try:
            from django.db import transaction

            with transaction.atomic():
                FormVersion.objects.select_for_update().get(pk=v)
                locked.set()
                time.sleep(0.6)  # the editor arrives while the publish is still open
                FormVersion.objects.filter(pk=v).update(status="published")
        finally:
            connection.close()

    def editor():
        try:
            locked.wait(5)
            try:
                Field(version_id=v, section=section, key="late_one", label="L",
                      type="short_text").save()
                outcome["result"] = "saved"
            except Exception as e:  # noqa: BLE001
                outcome["result"] = e.detail["code"] if hasattr(e, "detail") else repr(e)
        finally:
            connection.close()

    threads = [threading.Thread(target=publisher), threading.Thread(target=editor)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
    assert outcome["result"] == "VERSION_PUBLISHED"
    assert not Field.objects.filter(version_id=v, key="late_one").exists()


def test_failed_field_save_leaves_no_reserved_key_behind(make_form, tree):
    from django.db import IntegrityError

    from apps.forms.models import FieldKey, Section

    form = make_form()
    v = form["draft_version"]["id"]
    section = Section.objects.filter(version_id=v).first()
    bad = Field(version_id=v, section=section, key="ghost_key", label=None, type="short_text")  # type: ignore[misc]
    with pytest.raises(IntegrityError):  # label is NOT NULL
        bad.save()
    assert not FieldKey.objects.filter(form_id=form["id"], key="ghost_key").exists()


def test_booking_publish_is_blocked_when_it_would_break_a_published_inspection_rule(
        admin, make_form, tree, add_field):
    from django.core.management import call_command

    call_command("seed_master_lists")
    booking = make_form(key="booking", kind="booking")
    bv = booking["draft_version"]["id"]
    bs = tree(bv)["pages"][0]["sections"][0]["id"]
    add_field(bs, "fuel_type", type="single_choice",
              config={"options": [{"key": "cng", "label": "CNG"}]})
    assert publish_api(admin, bv).status_code == 200

    insp = make_form(key="pdi")
    iv = insp["draft_version"]["id"]
    is_ = tree(iv)["pages"][0]["sections"][0]["id"]
    add_field(is_, "hydro_test", type="date", show_if={"==": [V("booking.fuel_type"), "cng"]})
    assert publish_api(admin, iv).status_code == 200

    b2 = admin.post(f"/api/v1/forms/{booking['id']}/drafts").json()["id"]
    fuel = [f for p in tree(b2)["pages"] for s in p["sections"] for f in s["fields"]
            if f["key"] == "fuel_type"][0]
    assert admin.delete(f"/api/v1/fields/{fuel['id']}").status_code == 204
    r = publish_api(admin, b2)
    assert r.status_code == 400 and r.json()["code"] == "PUBLISH_BLOCKED"
    issue = [i for i in r.json()["issues"] if i["code"] == "UNKNOWN_FIELD"][0]
    assert issue["path"].startswith("forms.pdi.") and "booking.fuel_type" in issue["message"]
    assert FormVersion.objects.get(pk=b2).status == "draft"


def test_booking_publish_passes_when_dependents_still_resolve(admin, make_form, tree, add_field):
    from django.core.management import call_command

    call_command("seed_master_lists")
    booking = make_form(key="booking", kind="booking")
    bv = booking["draft_version"]["id"]
    bs = tree(bv)["pages"][0]["sections"][0]["id"]
    add_field(bs, "fuel_type", type="single_choice",
              config={"options": [{"key": "cng", "label": "CNG"}]})
    publish_api(admin, bv)
    insp = make_form(key="pdi")
    iv = insp["draft_version"]["id"]
    add_field(tree(iv)["pages"][0]["sections"][0]["id"], "hydro_test", type="date",
              show_if={"==": [V("booking.fuel_type"), "cng"]})
    publish_api(admin, iv)
    b2 = admin.post(f"/api/v1/forms/{booking['id']}/drafts").json()["id"]
    assert publish_api(admin, b2).status_code == 200


def test_dependents_check_ignores_forms_without_a_live_version_and_unrelated_problems(
        admin, make_form, tree, add_field):
    from django.core.management import call_command

    call_command("seed_master_lists")
    booking = make_form(key="booking", kind="booking")
    bv = booking["draft_version"]["id"]
    publish_api(admin, bv)
    # a form that was never published has no live version to protect
    make_form(key="draft_only")
    # a live form with a problem of its own (unknown *inspection* field) must not block booking
    insp = make_form(key="pdi")
    iv = insp["draft_version"]["id"]
    s = tree(iv)["pages"][0]["sections"][0]["id"]
    add_field(s, "later_one")
    Field.objects.filter(version_id=iv, key="later_one").update(
        show_if={"==": [V("inspection.ghost"), 1]})  # unknown *inspection* field: its own problem
    FormVersion.objects.filter(pk=iv).update(status="published")
    b2 = admin.post(f"/api/v1/forms/{booking['id']}/drafts").json()["id"]
    assert publish_api(admin, b2).status_code == 200
