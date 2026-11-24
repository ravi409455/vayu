"""The start (check-in) and end (wrap-up) system forms, the image field, automatic date/time."""
import base64
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.accounts.models import AuditLog
from apps.forms.models import Field, Form, FormAsset
from apps.media import storage
from apps.media.tests.conftest import s3  # noqa: F401  (in-memory S3 for the pictures)

from .test_promote import export, publish, staging, wipe  # noqa: F401

pytestmark = pytest.mark.django_db


def png(size=(8, 8), fmt="PNG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (10, 120, 60)).save(buf, fmt)
    return buf.getvalue()


def upload(admin, data: bytes, name="qr.png", ctype="image/png"):
    return admin.post("/api/v1/form-assets", {"file": SimpleUploadedFile(name, data, ctype)},
                      format="multipart")


@pytest.fixture
def start_form():
    return Form.objects.get(type="start")


@pytest.fixture
def end_form():
    return Form.objects.get(type="end")


def tree(admin, version):
    return admin.get(f"/api/v1/form-versions/{version}").json()


# ---------------------------------------------------------------- the system form

def test_the_start_and_end_forms_come_with_their_locked_fields(admin, start_form, end_form):
    t = tree(admin, start_form.versions.get().id)
    assert [p["title"] for p in t["pages"]] == ["Check-in"]
    assert t["pages"][0]["gate"] is True                     # check-in must be done first
    fields = {f["key"]: f for s in t["pages"][0]["sections"] for f in s["fields"]}
    assert all(f["is_system"] for f in fields.values())
    assert set(fields) == {"checkin_gps", "checkin_time", "selfie"}
    assert fields["checkin_gps"]["config"] == {"auto": True}
    assert fields["checkin_time"]["config"] == {"auto": True}
    assert fields["selfie"]["required"] is True and fields["selfie"]["config"]["capture"] == "camera"
    e = tree(admin, end_form.versions.get().id)
    assert [p["title"] for p in e["pages"]] == ["Wrap-up"] and e["pages"][0]["gate"] is False
    fields = {f["key"]: f for s in e["pages"][0]["sections"] for f in s["fields"]}
    assert set(fields) == {"taking_payment", "payment_mode", "payment_amount",
                           "payment_screenshot"}
    assert fields["taking_payment"]["type"] == "yes_no" and fields["taking_payment"]["required"]
    for k in ("payment_mode", "payment_amount", "payment_screenshot"):          # only when paying
        assert fields[k]["show_if"] == {"==": [{"var": "end.taking_payment"}, True]}
        assert fields[k]["required_if"] == fields[k]["show_if"]


def test_the_system_form_publishes_as_it_is_and_its_basics_cannot_be_removed_or_retyped(
        admin, start_form):
    v = start_form.versions.get()
    publish(admin, v.id)
    d = admin.post(f"/api/v1/forms/{start_form.id}/drafts").json()["id"]
    gps = next(f for p in tree(admin, d)["pages"] for s in p["sections"] for f in s["fields"]
               if f["key"] == "checkin_gps")
    assert admin.delete(f"/api/v1/fields/{gps['id']}").status_code in (400, 409)
    assert admin.patch(f"/api/v1/fields/{gps['id']}", {"config": {"auto": False}},
                       format="json").json()["code"] == "SYSTEM_FIELD"
    assert admin.patch(f"/api/v1/fields/{gps['id']}", {"label": "Where are you"},
                       format="json").status_code == 200                 # relabelling is fine
    page = tree(admin, d)["pages"][0]
    assert admin.delete(f"/api/v1/pages/{page['id']}").json()["code"] == "SYSTEM_FIELD"


def test_custom_fields_can_be_added_beside_the_locked_ones(admin, end_form):
    t = tree(admin, end_form.versions.get().id)
    sec = t["pages"][0]["sections"][0]["id"]
    r = admin.post(f"/api/v1/sections/{sec}/fields", {"key": "google_review", "label": "Review",
                   "type": "yes_no"}, format="json")
    assert r.status_code == 201 and r.json()["is_system"] is False


def test_system_fields_stay_on_their_page_when_dragged(admin, start_form):
    t = tree(admin, start_form.versions.get().id)
    extra = admin.post(f"/api/v1/form-versions/{t['id']}/pages", {"title": "Extra"},
                       format="json").json()
    extra_sec = admin.post(f"/api/v1/pages/{extra['id']}/sections", {"title": "More"},
                           format="json").json()
    first = t["pages"][0]["sections"][0]
    selfie = next(f for f in first["fields"] if f["key"] == "selfie")
    r = admin.post(f"/api/v1/form-versions/{t['id']}/reorder", {"fields": {
        str(extra_sec["id"]): [selfie["id"]]}}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "SYSTEM_FIELD"
    order = [f["id"] for f in first["fields"]]
    assert admin.post(f"/api/v1/form-versions/{t['id']}/reorder", {"fields": {
        str(first["id"]): list(reversed(order))}}, format="json").status_code == 200   # reorder ok


# ---------------------------------------------------------------- the image field

def test_a_picture_is_uploaded_shown_and_used_by_an_image_field(admin, end_form, api_as):
    r = upload(admin, png())
    assert r.status_code == 201
    asset = FormAsset.objects.get(pk=r.json()["id"])
    assert asset.content_type == "image/png" and storage.exists(asset.key)
    assert AuditLog.objects.filter(action="form.asset_upload").exists()
    shown = admin.get(r.json()["url"])
    assert shown.status_code == 302 and "form-assets" in shown["Location"]
    t = tree(admin, end_form.versions.get().id)
    sec = t["pages"][0]["sections"][0]["id"]
    made = admin.post(f"/api/v1/sections/{sec}/fields", {
        "key": "pay_qr", "label": "Scan to pay", "type": "image", "config": {"asset": str(asset.id)}},
        format="json")
    assert made.status_code == 201
    from apps.accounts.models import Role

    expert, _ = api_as(Role.EXPERT)
    assert expert.get(r.json()["url"]).status_code == 302               # anyone signed in sees it
    assert expert.post("/api/v1/form-assets", {}, format="multipart").status_code == 403


@pytest.mark.parametrize("data,ctype", [(b"", "image/png"), (b"not a picture", "image/png"),
                                        (png(fmt="GIF"), "image/gif"),
                                        (png() + b"0" * (2 * 1024 * 1024), "image/png")],
                         ids=["empty", "not-a-picture", "gif", "over-2mb"])
def test_only_small_real_png_or_jpeg_pictures_are_accepted(admin, data, ctype):
    r = upload(admin, data, ctype=ctype)
    assert r.status_code == 400 and r.json()["code"] == "INVALID_IMAGE"
    assert not FormAsset.objects.exists()


def test_a_jpeg_is_accepted_and_a_missing_file_is_refused(admin):
    assert upload(admin, png(fmt="JPEG"), "a.jpg", "image/jpeg").status_code == 201
    assert FormAsset.objects.get().content_type == "image/jpeg"
    assert admin.post("/api/v1/form-assets", {}, format="multipart").status_code == 400


def test_an_image_field_needs_an_uploaded_picture_and_takes_no_answers(admin, end_form):
    t = tree(admin, end_form.versions.get().id)
    sec = t["pages"][0]["sections"][0]["id"]
    for config in ({}, {"asset": "nope"}, {"asset": "11111111-1111-1111-1111-111111111111"}):
        r = admin.post(f"/api/v1/sections/{sec}/fields", {"key": "pay_qr", "label": "x",
                       "type": "image", "config": config}, format="json")
        assert r.status_code == 400 and r.json()["code"] == "INVALID_CONFIG"
    from apps.forms.fieldtypes import AnswerError, clean_answer

    field = Field(type="image", config={})
    with pytest.raises(AnswerError):
        clean_answer(field, "anything")


def test_automatic_settings_must_be_true_or_false(admin, end_form):
    t = tree(admin, end_form.versions.get().id)
    sec = t["pages"][0]["sections"][0]["id"]
    ok = admin.post(f"/api/v1/sections/{sec}/fields", {"key": "when", "label": "When",
                    "type": "datetime", "config": {"auto": True}}, format="json")
    assert ok.status_code == 201
    bad = admin.post(f"/api/v1/sections/{sec}/fields", {"key": "when2", "label": "When",
                     "type": "date", "config": {"auto": "yes"}}, format="json")
    assert bad.status_code == 400
    no = admin.post(f"/api/v1/sections/{sec}/fields", {"key": "name2", "label": "N",
                    "type": "short_text", "config": {"auto": True}}, format="json")
    assert no.status_code == 400                                          # only date/time/gps


def test_pictures_travel_inside_the_promote_bundle(admin, staging):
    asset = FormAsset.objects.get(pk=upload(admin, png()).json()["id"])
    d = admin.post(f"/api/v1/forms/{staging['form']['id']}/drafts").json()["id"]
    page = tree(admin, d)["pages"][0]
    sec = page["sections"][0]["id"]
    assert admin.post(f"/api/v1/sections/{sec}/fields", {"key": "qr", "label": "QR",
                      "type": "image", "config": {"asset": str(asset.id)}}, format="json"
                      ).status_code == 201
    publish(admin, d)
    bundle = export(admin, d)
    assert list(bundle["assets"]) == [str(asset.id)]
    assert base64.b64decode(bundle["assets"][str(asset.id)]["data"]) == png()
    wipe()
    FormAsset.objects.all().delete()
    r = admin.post("/api/v1/promote/import", bundle, format="json")
    assert r.status_code == 201, r.content
    new = FormAsset.objects.get()
    assert str(new.id) != str(asset.id)                       # a new id on this server
    field = Field.objects.get(version_id=r.json()["draft_version"], key="qr")
    assert field.config["asset"] == str(new.id) and storage.exists(new.key)


def test_damaged_pictures_in_a_bundle_are_refused(admin, staging):
    d = admin.post(f"/api/v1/forms/{staging['form']['id']}/drafts").json()["id"]
    bundle = export(admin, staging["version"])
    wipe()
    del d
    for bad in ({"x": {"content_type": "image/png", "data": "!!!"}}, {"x": {"data": "aGk="}},
                {"x": "nope"}, [1], "x"):
        bundle["assets"] = bad
        r = admin.post("/api/v1/promote/import", bundle, format="json")
        assert r.status_code == 400 and r.json()["code"] in ("INVALID_BUNDLE", "INVALID_IMAGE"), bad


def test_a_system_form_promotes_into_the_system_form_of_the_same_type(admin, start_form):
    v = start_form.versions.get().id
    publish(admin, v)
    bundle = export(admin, v)
    assert bundle["form"]["type"] == "start" and "slot" not in bundle["version"]["pages"][0]
    bundle["form"]["key"] = "some_other_key"                 # found by type, whatever it is called
    r = admin.post("/api/v1/promote/import", bundle, format="json")
    assert r.status_code == 201, r.content
    assert Form.objects.filter(type="start").count() == 1
    assert Form.objects.get(type="start").versions.count() == 2
    assert admin.patch(f"/api/v1/forms/{start_form.id}", {"is_active": False},
                       format="json").json()["code"] == "SYSTEM_FORM"


def test_submission_visibility_travels_and_bad_values_are_refused(admin, staging):
    admin.patch(f"/api/v1/forms/{staging['form']['id']}", {"submission_roles": ["ops"]},
                format="json")
    bundle = export(admin, staging["version"])
    assert bundle["form"]["submission_roles"] == ["ops"]
    wipe()
    assert admin.post("/api/v1/promote/import", bundle, format="json").status_code == 201
    assert Form.objects.get(key="pdi").submission_roles == ["ops"]
    wipe()
    bundle["form"]["submission_roles"] = ["admin"]
    assert admin.post("/api/v1/promote/import", bundle, format="json").json()["code"] == \
        "INVALID_BUNDLE"


def test_payment_fields_are_ordinary_fields_the_admin_may_change_or_remove(admin, end_form):
    """Payment is forms like any other (owner, 2026-11-24): no locked payment fields."""
    v = end_form.versions.get()
    publish(admin, v.id)
    d = admin.post(f"/api/v1/forms/{end_form.id}/drafts").json()["id"]
    fields = {f["key"]: f for p in tree(admin, d)["pages"] for s in p["sections"]
              for f in s["fields"]}
    assert not any(f["is_system"] for f in fields.values())
    mode = fields["payment_mode"]
    assert admin.patch(f"/api/v1/fields/{mode['id']}", {"required": True},
                       format="json").status_code == 200
    assert admin.delete(f"/api/v1/fields/{fields['payment_screenshot']['id']}").status_code == 204


def test_existing_payment_fields_are_unlocked_by_the_data_fix(end_form):
    import importlib

    from django.apps import apps as live
    fix = importlib.import_module("apps.forms.migrations.0019_payment_fields_ordinary")
    Field.objects.filter(key="payment_mode").update(is_system=True)
    fix.unlock(live, None)
    assert not Field.objects.filter(key__in=fix.KEYS, is_system=True).exists()
