"""Ops (and Admin) add or replace photos and videos once the expert has submitted; they never
delete, a replaced file is kept for Admin, and the Admin can block a field."""
from unittest import mock

import pytest

from apps.bookings.models import BookingActivity, Inspection
from apps.forms.models import Field
from apps.media.models import MediaAsset, MediaZip
from apps.media.tests.conftest import initiate_body, jpeg, upload
from apps.media.tests.test_upload import job, menv, submit_with  # noqa: F401

pytestmark = pytest.mark.django_db


def submitted(env, b, settings, n=1):
    ids = [upload(env.expert, b["id"], jpeg(color=(i, 9, 9)), settings).json()["id"]
           for i in range(n)]
    assert submit_with(env, b, photo_a=ids).status_code == 200
    return ids


def ops_upload(env, b, settings, client=None, **kw):
    r = upload(client or env.ops, b["id"], jpeg(color=(77, 1, 1)), settings, source="gallery",
               **kw)
    return r


def photos(b):
    return Inspection.objects.get(booking_id=b["id"]).answers["inspection"].get("photo_a")


def test_ops_replace_swaps_the_file_and_keeps_the_old_one_for_admin(job, settings):
    env, b = job
    [old] = submitted(env, b, settings)
    env.ops.post(f"/api/v1/bookings/{b['id']}/media-zip", {"kind": "image"}, format="json")
    new = ops_upload(env, b, settings, replaces=old).json()["id"]
    with mock.patch("apps.reports.tasks.render_report.delay") as render:
        r = env.ops.post(f"/api/v1/media/{new}/attach", {"replaces": old}, format="json")
    assert r.status_code == 204
    assert photos(b) == [new]
    gone = MediaAsset.objects.get(pk=old)
    assert str(gone.replaced_by_id) == new and gone.replaced_at is not None   # kept, not deleted
    assert MediaZip.objects.count() == 0
    render.assert_not_called()          # completed: the PDF is only marked out of date (F-219)
    assert env.admin.get(f"/api/v1/media/{old}/url").status_code == 200
    assert env.ops.get(f"/api/v1/media/{old}/url").status_code == 404        # history: Admin
    row = BookingActivity.objects.get(kind="media_replaced")
    assert row.changes == {"media": [old, new]} and row.keys == ["inspection.photo_a"]
    ops_rows = env.ops.get(f"/api/v1/bookings/{b['id']}/activity").json()
    mine = next(x for x in ops_rows if x["kind"] == "media_replaced")
    assert mine["changes"] == {} and mine["keys"] == ["inspection.photo_a"]   # no old file link
    admin_rows = env.admin.get(f"/api/v1/bookings/{b['id']}/activity").json()
    assert next(x for x in admin_rows if x["kind"] == "media_replaced")["changes"]["media"][0] == old
    listed = env.ops.get(f"/api/v1/bookings/{b['id']}/media").json()
    assert [(x["id"], x["by_ops"]) for x in listed] == [(new, True)]


def test_a_full_field_can_be_replaced_but_not_added_to(job, settings):
    env, b = job
    a, c = submitted(env, b, settings, n=2)                  # photo_a takes at most 2
    r = env.ops.post("/api/v1/media/initiate", initiate_body(b["id"], jpeg()), format="json")
    assert r.status_code == 409 and r.json()["code"] == "TOO_MANY"
    new = ops_upload(env, b, settings, replaces=c).json()["id"]
    assert env.ops.post(f"/api/v1/media/{new}/attach", {"replaces": c},
                        format="json").status_code == 204
    assert photos(b) == [a, new]


def test_ops_add_to_a_field_with_room(job, settings):
    env, b = job
    [a] = submitted(env, b, settings)
    new = ops_upload(env, b, settings).json()["id"]
    assert env.ops.post(f"/api/v1/media/{new}/attach", {}, format="json").status_code == 204
    assert env.ops.post(f"/api/v1/media/{new}/attach", {}, format="json").status_code == 204  # retry
    assert photos(b) == [a, new]
    assert BookingActivity.objects.filter(kind="media_added").count() == 1


def test_ops_cannot_upload_before_the_expert_submits(job):
    env, b = job
    r = env.ops.post("/api/v1/media/initiate", initiate_body(b["id"], jpeg()), format="json")
    assert r.status_code == 409 and r.json()["code"] == "NOT_SUBMITTED"


def test_admin_can_block_ops_uploads_on_a_field_admin_too(job, settings):
    env, b = job
    [a] = submitted(env, b, settings)
    f = Field.objects.get(key="photo_a")
    Field.objects.filter(pk=f.pk).update(config={**f.config, "ops_upload": False})
    for client in (env.ops, env.admin):
        r = client.post("/api/v1/media/initiate", initiate_body(b["id"], jpeg(), replaces=a),
                        format="json")
        assert r.status_code == 403 and r.json()["code"] == "OPS_UPLOAD_BLOCKED"


def test_ops_upload_must_be_a_boolean_in_the_field_config():
    from apps.forms.fieldtypes import ConfigError, validate_config

    validate_config("video", {"ops_upload": False})
    with pytest.raises(ConfigError):
        validate_config("photo", {"ops_upload": "no"})


def test_ops_cannot_add_signatures(job, settings):
    env, b = job
    submitted(env, b, settings)
    r = env.ops.post("/api/v1/media/initiate", initiate_body(
        b["id"], jpeg(), field_key="sign", kind="signature", content_type="image/png"),
        format="json")
    assert r.status_code == 403 and r.json()["code"] == "OPS_UPLOAD_NOT_ALLOWED"


PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def test_ops_add_and_replace_a_document(job, settings):
    env, b = job
    submitted(env, b, settings)
    first = upload(env.ops, b["id"], PDF, settings, field_key="doc", kind="file",
                   content_type="application/pdf", source="gallery").json()["id"]
    assert env.ops.post(f"/api/v1/media/{first}/attach", {}, format="json").status_code == 204
    pic = upload(env.ops, b["id"], jpeg(), settings, field_key="doc", kind="file",
                 source="gallery", replaces=first).json()["id"]
    assert env.ops.post(f"/api/v1/media/{pic}/attach", {"replaces": first},
                        format="json").status_code == 204
    answers = Inspection.objects.get(booking_id=b["id"]).answers["inspection"]
    assert answers["doc"] == [pic]
    links = env.ops.get(f"/api/v1/media/{pic}/url").json()
    assert links["content_type"] == "image/jpeg" and links["preview_url"]   # a picture: preview


def test_a_file_field_takes_only_the_kinds_admin_allowed(job, settings):
    env, b = job
    f = Field.objects.get(key="doc")
    Field.objects.filter(pk=f.pk).update(config={**f.config, "allowed": ["pdf"]})

    def picture(client):
        r = client.post("/api/v1/media/initiate", initiate_body(
            b["id"], jpeg(), field_key="doc", kind="file"), format="json")
        assert r.status_code == 400 and r.json()["code"] == "INVALID_CONTENT_TYPE"
    picture(env.expert)                       # the expert, while working
    submitted(env, b, settings)
    picture(env.ops)                          # Ops, after submit


def test_admin_can_block_ops_uploads_on_a_file_field():
    from apps.forms.fieldtypes import ConfigError, validate_config

    validate_config("file", {"ops_upload": False})
    with pytest.raises(ConfigError):
        validate_config("file", {"ops_upload": 0})


def test_replace_must_name_a_live_file_of_the_same_field(job, settings):
    env, b = job
    [a] = submitted(env, b, settings)
    new = ops_upload(env, b, settings, replaces=a).json()["id"]
    env.ops.post(f"/api/v1/media/{new}/attach", {"replaces": a}, format="json")
    again = env.ops.post("/api/v1/media/initiate", initiate_body(b["id"], jpeg(), replaces=a),
                         format="json")
    assert again.status_code == 400 and again.json()["code"] == "UNKNOWN_MEDIA"   # already replaced
    bad = env.ops.post("/api/v1/media/initiate", initiate_body(b["id"], jpeg(),
                       replaces="not-a-uuid"), format="json")
    assert bad.status_code == 400
    other = ops_upload(env, b, settings).json()["id"]
    r = env.ops.post(f"/api/v1/media/{other}/attach", {"replaces": a}, format="json")
    assert r.status_code == 400 and photos(b) == [new]


def test_a_file_still_uploading_cannot_be_attached(job, settings):
    env, b = job
    [a] = submitted(env, b, settings)
    r = env.ops.post("/api/v1/media/initiate", initiate_body(b["id"], jpeg(), replaces=a),
                     format="json")
    new = r.json()["id"]                                       # registered, bytes not sent yet
    r = env.ops.post(f"/api/v1/media/{new}/attach", {"replaces": a}, format="json")
    assert r.status_code == 409 and r.json()["code"] == "UPLOAD_NOT_FINISHED"
    assert photos(b) == [a]                                    # the good file stays


def test_experts_cannot_attach(job, settings):
    env, b = job
    [a] = submitted(env, b, settings)
    new = ops_upload(env, b, settings).json()["id"]
    assert env.expert.post(f"/api/v1/media/{new}/attach", {}, format="json").status_code == 403


def test_a_never_attached_ops_upload_can_be_taken_back(job, settings):
    env, b = job
    submitted(env, b, settings)
    new = ops_upload(env, b, settings).json()["id"]
    assert env.ops.delete(f"/api/v1/media/{new}").status_code == 204


def test_files_left_out_of_the_answers_do_not_count_against_ops(job, settings):
    env, b = job
    a = upload(env.expert, b["id"], jpeg(), settings).json()["id"]
    upload(env.expert, b["id"], jpeg(color=(1, 1, 1)), settings)    # a retake left behind
    assert submit_with(env, b, photo_a=[a]).status_code == 200
    new = ops_upload(env, b, settings).json()["id"]                  # 1 of 2 in the answers: room
    assert env.ops.post(f"/api/v1/media/{new}/attach", {}, format="json").status_code == 204
    swap = ops_upload(env, b, settings, replaces=a).json()["id"]
    assert env.ops.post(f"/api/v1/media/{swap}/attach", {"replaces": a},
                        format="json").status_code == 204
    assert photos(b) == [swap, new]


def test_experts_cannot_ask_to_replace(job, settings):
    env, b = job
    a = upload(env.expert, b["id"], jpeg(), settings).json()["id"]
    r = env.expert.post("/api/v1/media/initiate", initiate_body(b["id"], jpeg(), replaces=a),
                        format="json")
    assert r.status_code == 400 and r.json()["code"] == "UNKNOWN_MEDIA"


@pytest.mark.django_db(transaction=True, serialized_rollback=True)   # real commits: the edit must open its own transaction
def test_an_inspection_edit_cannot_drop_a_file_but_can_add_one(job, settings):
    env, b = job
    [a] = submitted(env, b, settings)
    insp = Inspection.objects.get(booking_id=b["id"])
    r = env.ops.patch(f"/api/v1/inspections/{insp.id}", {"row_version": insp.row_version,
                      "answers": {"inspection": {"photo_a": []}}}, format="json")
    assert r.status_code == 403 and r.json()["code"] == "FILE_REMOVAL_NOT_ALLOWED"
    new = ops_upload(env, b, settings).json()["id"]                 # the Android app's way to add
    r = env.ops.patch(f"/api/v1/inspections/{insp.id}", {"row_version": insp.row_version,
                      "answers": {"inspection": {"photo_a": [a, new]}}}, format="json")
    assert r.status_code == 200 and photos(b) == [a, new]


def test_ops_cannot_upload_to_a_field_hidden_from_them(job, settings):
    env, b = job
    [a] = submitted(env, b, settings)
    Field.objects.filter(key="photo_a").update(access={"ops": {"completed": "hidden"}})
    r = env.ops.post("/api/v1/media/initiate", initiate_body(b["id"], jpeg(), replaces=a),
                     format="json")
    assert r.status_code == 400 and r.json()["code"] == "UNKNOWN_FIELD"


def test_ops_cannot_upload_to_a_field_read_only_for_them(job, settings):
    env, b = job
    [a] = submitted(env, b, settings)
    Field.objects.filter(key="photo_a").update(access={"ops": {"completed": "view"}})
    r = env.ops.post("/api/v1/media/initiate", initiate_body(b["id"], jpeg(), replaces=a),
                     format="json")
    assert r.status_code == 403 and r.json()["code"] == "FIELD_ACCESS"


def test_loose_ops_uploads_are_capped(job, settings):
    from apps.media import services

    env, b = job
    [a] = submitted(env, b, settings)
    settings_cap, services.LOOSE_LIMIT = services.LOOSE_LIMIT, 2
    try:
        for _ in range(2):              # started, never attached (a closed tab)
            assert env.ops.post("/api/v1/media/initiate", initiate_body(
                b["id"], jpeg(), replaces=a), format="json").status_code == 201
        r = env.ops.post("/api/v1/media/initiate", initiate_body(b["id"], jpeg(), replaces=a),
                         format="json")
        assert r.status_code == 409 and r.json()["code"] == "TOO_MANY"
    finally:
        services.LOOSE_LIMIT = settings_cap


def test_an_inspection_edit_adds_only_own_files_on_unblocked_fields(job, settings):
    env, b = job
    stray = upload(env.expert, b["id"], jpeg(color=(5, 5, 5)), settings)   # expert's retake
    [a] = submitted(env, b, settings)
    insp = Inspection.objects.get(booking_id=b["id"])
    r = env.ops.patch(f"/api/v1/inspections/{insp.id}", {"row_version": insp.row_version,
                      "answers": {"inspection": {"photo_a": [a, stray.json()["id"]]}}},
                      format="json")
    assert r.status_code == 400 and r.json()["code"] == "UNKNOWN_MEDIA"
    mine = ops_upload(env, b, settings).json()["id"]
    f = Field.objects.get(key="photo_a")
    Field.objects.filter(pk=f.pk).update(config={**f.config, "ops_upload": False})
    r = env.ops.patch(f"/api/v1/inspections/{insp.id}", {"row_version": insp.row_version,
                      "answers": {"inspection": {"photo_a": [a, mine]}}}, format="json")
    assert r.status_code == 403 and r.json()["code"] == "OPS_UPLOAD_BLOCKED"
    assert photos(b) == [a]
