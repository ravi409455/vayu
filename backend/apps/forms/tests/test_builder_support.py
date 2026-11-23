"""What the form builder screen needs: page gates, capture modes, drag reordering, discarding."""
import pytest

from apps.accounts.models import AuditLog
from apps.forms.models import Field, FormVersion, Page, Section

from .test_promote import export, publish, staging, wipe  # noqa: F401

pytestmark = pytest.mark.django_db


def tree(admin, version):
    return admin.get(f"/api/v1/form-versions/{version}").json()


def draft_of(admin, staging):
    form = staging["form"]
    d = admin.post(f"/api/v1/forms/{form['id']}/drafts").json()["id"]
    return form["id"], d


# ---------------------------------------------------------------- page gate and capture mode

def test_a_page_can_require_completion_before_moving_on(admin, staging):
    _, d = draft_of(admin, staging)
    page = tree(admin, d)["pages"][0]
    assert page["gate"] is False
    r = admin.patch(f"/api/v1/pages/{page['id']}", {"gate": True}, format="json")
    assert r.status_code == 200 and r.json()["gate"] is True
    assert tree(admin, d)["pages"][0]["gate"] is True


def test_the_gate_survives_a_new_draft_publish_and_promotion(admin, staging):
    form_id, d = draft_of(admin, staging)
    page = tree(admin, d)["pages"][0]
    admin.patch(f"/api/v1/pages/{page['id']}", {"gate": True}, format="json")
    publish(admin, d)
    nd = admin.post(f"/api/v1/forms/{form_id}/drafts").json()["id"]
    assert tree(admin, nd)["pages"][0]["gate"] is True                    # copied into the next draft
    bundle = export(admin, d)
    assert bundle["version"]["pages"][0]["gate"] is True
    admin.delete(f"/api/v1/forms/{form_id}/draft")
    wipe()
    r = admin.post("/api/v1/promote/import", bundle, format="json")
    assert r.status_code == 201
    assert Page.objects.get(version_id=r.json()["draft_version"]).gate is True


def test_an_older_bundle_without_gates_still_imports_and_a_bad_gate_is_refused(admin, staging):
    bundle = export(admin, staging["version"])
    wipe()
    for p in bundle["version"]["pages"]:
        p.pop("gate")
    assert admin.post("/api/v1/promote/import", bundle, format="json").status_code == 201
    wipe()
    bundle["version"]["pages"][0]["gate"] = "yes"
    r = admin.post("/api/v1/promote/import", bundle, format="json")
    assert r.status_code == 400 and r.json()["code"] == "INVALID_BUNDLE"


@pytest.mark.parametrize("type_,mode,ok", [("photo", "both", True), ("photo", "camera", True),
                                           ("photo", "upload", True), ("video", "camera", True),
                                           ("photo", "gallery", False), ("video", 3, False)])
def test_photo_and_video_fields_choose_how_files_are_added(admin, staging, type_, mode, ok):
    _, d = draft_of(admin, staging)
    sec = tree(admin, d)["pages"][0]["sections"][0]["id"]
    r = admin.post(f"/api/v1/sections/{sec}/fields", {
        "key": f"f_{type_}_{mode}", "label": "x", "type": type_,
        "config": {"max_count": 2, "capture": mode}}, format="json")
    assert (r.status_code == 201) is ok
    if not ok:
        assert r.json()["code"] == "INVALID_CONFIG"


# ---------------------------------------------------------------- drag reordering

def test_reordering_pages_sections_and_fields_in_one_step(admin, staging):
    _, d = draft_of(admin, staging)
    page2 = admin.post(f"/api/v1/form-versions/{d}/pages", {"title": "Second"}, format="json").json()
    t = tree(admin, d)
    first = t["pages"][0]
    secs = [s["id"] for s in first["sections"]]
    fields = [f["id"] for f in first["sections"][0]["fields"]]
    r = admin.post(f"/api/v1/form-versions/{d}/reorder", {
        "pages": [page2["id"], first["id"]],
        "sections": {str(first["id"]): list(reversed(secs))},
        "fields": {str(secs[0]): list(reversed(fields))}}, format="json")
    assert r.status_code == 200 and r.json()["row_version"] > t["row_version"]
    after = tree(admin, d)
    assert [p["id"] for p in after["pages"]] == [page2["id"], first["id"]]
    again = next(p for p in after["pages"] if p["id"] == first["id"])
    assert [s["id"] for s in again["sections"]] == list(reversed(secs))
    sec0 = next(s for s in again["sections"] if s["id"] == secs[0])
    assert [f["id"] for f in sec0["fields"]] == list(reversed(fields))
    assert AuditLog.objects.filter(action="form.reorder").exists()


def test_a_field_and_a_section_can_move_to_another_container(admin, staging):
    _, d = draft_of(admin, staging)
    page2 = admin.post(f"/api/v1/form-versions/{d}/pages", {"title": "Second"}, format="json").json()
    sec_new = admin.post(f"/api/v1/pages/{page2['id']}/sections", {"title": "New"},
                         format="json").json()
    t = tree(admin, d)
    first = t["pages"][0]
    plain = next(s for s in first["sections"] if not s["locked"])
    moving = next(f for f in plain["fields"] if f["key"] == "door")
    assert admin.post(f"/api/v1/form-versions/{d}/reorder", {"fields": {
        str(sec_new["id"]): [moving["id"]]}}, format="json").status_code == 200
    assert Field.objects.get(pk=moving["id"]).section_id == sec_new["id"]
    brakes = next(s for s in first["sections"] if s["locked"])
    assert admin.post(f"/api/v1/form-versions/{d}/reorder", {"sections": {
        str(page2["id"]): [sec_new["id"], brakes["id"]]}}, format="json").status_code == 200
    assert Section.objects.get(pk=brakes["id"]).page_id == page2["id"]


def test_fields_cannot_move_into_or_out_of_a_library_section(admin, staging):
    _, d = draft_of(admin, staging)
    first = tree(admin, d)["pages"][0]
    linked = next(s for s in first["sections"] if s["locked"])
    plain = next(s for s in first["sections"] if not s["locked"])
    door = next(f for f in plain["fields"] if f["key"] == "door")
    r = admin.post(f"/api/v1/form-versions/{d}/reorder", {"fields": {
        str(linked["id"]): [door["id"]]}}, format="json")
    assert r.status_code == 409 and r.json()["code"] == "LINKED_LOCKED"


@pytest.mark.parametrize("body", [
    [], {"nope": 1}, {"pages": "x"}, {"pages": [1, 1]}, {"pages": [True]}, {"pages": [999999]},
    {"sections": {"abc": []}}, {"sections": {"999999": []}}, {"fields": {"999999": []}},
    {"fields": {"1": [999999]}}, {"sections": {"1": [999999]}}])
def test_bad_reorder_requests_are_refused(admin, staging, body):
    _, d = draft_of(admin, staging)
    page = tree(admin, d)["pages"][0]
    if isinstance(body, dict) and "sections" in body and "1" in body["sections"]:
        body = {"sections": {str(page["id"]): [999999]}}
    if isinstance(body, dict) and "fields" in body and "1" in body["fields"]:
        body = {"fields": {str(page["sections"][0]["id"]): [999999]}}
    r = admin.post(f"/api/v1/form-versions/{d}/reorder", body, format="json")
    assert r.status_code == 400, r.content


def test_reordering_needs_a_draft_and_edit_rights(admin, staging, api_as):
    from apps.accounts.models import Role

    published = staging["version"]
    r = admin.post(f"/api/v1/form-versions/{published}/reorder", {"pages": []}, format="json")
    assert r.status_code == 409 and r.json()["code"] == "VERSION_PUBLISHED"
    ops, _ = api_as(Role.OPS)
    assert ops.post(f"/api/v1/form-versions/{published}/reorder", {}, format="json").status_code == 403


# ---------------------------------------------------------------- discarding a draft

def test_discarding_a_draft_keeps_the_published_version(admin, staging):
    form_id, d = draft_of(admin, staging)
    assert admin.delete(f"/api/v1/forms/{form_id}/draft").status_code == 204
    assert not FormVersion.objects.filter(pk=d).exists()
    assert FormVersion.objects.filter(pk=staging["version"], status="published").exists()
    assert admin.get(f"/api/v1/forms/{form_id}").json()["draft_version"] is None
    assert AuditLog.objects.filter(action="form.draft_discard").exists()
    nd = admin.post(f"/api/v1/forms/{form_id}/drafts")                    # a new draft is possible again
    assert nd.status_code == 201 and nd.json()["number"] == 2


def test_discard_refusals(admin, staging, api_as):
    from apps.accounts.models import Role

    form_id = staging["form"]["id"]
    r = admin.delete(f"/api/v1/forms/{form_id}/draft")
    assert r.status_code == 409 and r.json()["code"] == "NO_DRAFT"
    ops, _ = api_as(Role.OPS)
    assert ops.delete(f"/api/v1/forms/{form_id}/draft").status_code == 403
    new = admin.post("/api/v1/forms", {"key": "fresh", "kind": "inspection", "name": "Fresh"},
                     format="json").json()
    r = admin.delete(f"/api/v1/forms/{new['id']}/draft")
    assert r.status_code == 409 and r.json()["code"] == "FIRST_DRAFT"


def test_a_form_itself_can_never_be_deleted(admin, staging):
    assert admin.delete(f"/api/v1/forms/{staging['form']['id']}").status_code == 405
