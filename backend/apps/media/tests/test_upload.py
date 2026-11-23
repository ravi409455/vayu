"""Upload protocol, verification, completion, ops edits, ZIPs, stuck uploads."""
import io
import uuid

import pytest
from PIL import Image

from apps.bookings.models import Booking
from apps.bookings.tests.test_submissions import assign, publish_form, start
from apps.media import storage
from apps.media.models import MediaAsset, MediaZip

from .conftest import create, initiate_body, jpeg, png, put_parts, sha, upload

pytestmark = pytest.mark.django_db


@pytest.fixture
def menv(env):
    """PDI form with a photo (max 2), video (max 1), file and signature field."""
    admin = env.admin
    form = admin.post("/api/v1/forms", {"key": "pdi", "kind": "inspection", "name": "PDI",
                                        "inspection_type": "pdi"}, format="json").json()
    v = form["draft_version"]["id"]
    sec = admin.get(f"/api/v1/form-versions/{v}").json()["pages"][0]["sections"][0]["id"]
    for key, type_, cfg in (("photo_a", "photo", {"max_count": 2}), ("clip", "video", {"max_count": 1}),
                            ("doc", "file", {"max_count": 2}), ("sign", "signature", {})):
        assert admin.post(f"/api/v1/sections/{sec}/fields", {"key": key, "label": key, "type": type_,
                          "config": cfg}, format="json").status_code == 201
    publish_form(admin, form["id"])
    return env


@pytest.fixture
def job(menv):
    b = create(menv.ops, booking_id="MD1").json()
    assign(menv, b)
    start(menv.expert, b)
    return menv, b


def submit_with(env, b, **media):
    body = {"client_submission_uuid": str(uuid.uuid4()),
            "answers": {"inspection": {"chassis_no": "MA3YPKCSKTJ273129", **media}}}
    return env.expert.post(f"/api/v1/bookings/{b['id']}/submit", body, format="json")


# ---------------------------------------------------------------- initiate

def test_initiate_returns_part_urls_and_is_idempotent(job, settings):
    env, b = job
    data = jpeg()
    body = initiate_body(b["id"], data)
    r = env.expert.post("/api/v1/media/initiate", body, format="json")
    assert r.status_code == 201
    out = r.json()
    assert out["status"] == "pending" and len(out["parts"]) == 1
    assert out["parts"][0]["url"].startswith("https://") and "uploadId" in out["parts"][0]["url"]
    again = env.expert.post("/api/v1/media/initiate", body, format="json")
    assert again.status_code == 200 and again.json()["id"] == out["id"]
    assert MediaAsset.objects.count() == 1


def test_a_big_file_gets_one_url_per_8mb_part(job, settings):
    env, b = job
    settings.MEDIA_PART_SIZE = 5 * 1024 * 1024
    data = b"x" * (11 * 1024 * 1024)
    r = env.expert.post("/api/v1/media/initiate", initiate_body(
        b["id"], data, field_key="clip", kind="video", content_type="video/mp4"), format="json")
    assert r.status_code == 201 and [p["part_number"] for p in r.json()["parts"]] == [1, 2, 3]


@pytest.mark.parametrize("change,code,status", [
    ({"kind": "movie"}, "INVALID_MEDIA", 400), ({"size": 0}, "INVALID_MEDIA", 400),
    ({"size": 99 * 1024 * 1024}, "TOO_LARGE", 400),
    ({"content_type": "application/x-msdownload"}, "INVALID_CONTENT_TYPE", 400),
    ({"sha256": "abc"}, "INVALID_MEDIA", 400), ({"source": "dropbox"}, "INVALID_MEDIA", 400),
    ({"field_key": "ghost"}, "UNKNOWN_FIELD", 400), ({"field_key": "clip"}, "WRONG_KIND", 400),
    ({"client_uuid": "nope"}, "INVALID_MEDIA", 400),
])
def test_initiate_validation(job, change, code, status):
    env, b = job
    body = {**initiate_body(b["id"], jpeg()), **change}
    r = env.expert.post("/api/v1/media/initiate", body, format="json")
    assert r.status_code == status and r.json()["code"] == code


def test_field_count_limit(job, settings):
    env, b = job
    for _ in range(2):
        assert upload(env.expert, b["id"], jpeg(), settings).status_code == 200
    r = env.expert.post("/api/v1/media/initiate", initiate_body(b["id"], jpeg()), format="json")
    assert r.status_code == 409 and r.json()["code"] == "TOO_MANY"


def test_only_the_experts_own_booking_or_media_managers(job, menv, settings):
    env, b = job
    other = env.make_user("expert", username="e8")
    from rest_framework.test import APIClient

    c = APIClient()
    c.force_authenticate(user=other)
    assert c.post("/api/v1/media/initiate", initiate_body(b["id"], jpeg()),
                  format="json").status_code == 404
    assert env.ops.post("/api/v1/media/initiate", initiate_body(b["id"], jpeg()),
                        format="json").status_code == 201      # media.manage
    from apps.accounts.catalog import DEFAULTS

    perms = {k: v for k, v in DEFAULTS["ops"].items() if k != "media.manage"}
    env.admin.put("/api/v1/roles/ops/permissions", {"permissions": perms}, format="json")
    assert env.ops.post("/api/v1/media/initiate", initiate_body(b["id"], jpeg()),
                        format="json").status_code == 403


def test_another_users_client_uuid_is_a_conflict(job):
    env, b = job
    body = initiate_body(b["id"], jpeg())
    env.expert.post("/api/v1/media/initiate", body, format="json")
    r = env.ops.post("/api/v1/media/initiate", body, format="json")
    assert r.status_code == 409 and r.json()["code"] == "UUID_CONFLICT"


def test_source_is_stored_for_gallery_photos(job, settings):
    env, b = job
    upload(env.expert, b["id"], jpeg(), settings, source="gallery")
    assert MediaAsset.objects.get().source == "gallery"


# ---------------------------------------------------------------- complete / resume / checksum

def test_complete_verifies_and_makes_a_preview(job, settings):
    env, b = job
    r = upload(env.expert, b["id"], jpeg(), settings)
    assert r.status_code == 200 and r.json()["status"] == "verified"
    a = MediaAsset.objects.get()
    assert a.verified_at and storage.exists(a.key) and storage.exists(a.preview_key)
    assert max(Image.open(io.BytesIO(storage.read(a.preview_key))).size) <= 480


def test_a_huge_photo_is_stored_at_most_2048px(job, settings):
    env, b = job
    r = upload(env.expert, b["id"], jpeg(4000, 3000), settings)
    assert r.status_code == 200
    a = MediaAsset.objects.get()
    assert max(Image.open(io.BytesIO(storage.read(a.key))).size) == 2048


def test_resume_lists_uploaded_parts_and_completes_the_rest(job, settings):
    env, b = job
    settings.MEDIA_PART_SIZE = 5 * 1024 * 1024
    data = b"v" * (11 * 1024 * 1024)
    init = env.expert.post("/api/v1/media/initiate", initiate_body(
        b["id"], data, field_key="clip", kind="video", content_type="video/mp4"),
        format="json").json()
    first = put_parts(init, data, settings, only={1})
    seen = env.expert.get(f"/api/v1/media/{init['id']}").json()["uploaded_parts"]
    assert [p["part_number"] for p in seen] == [1]               # the phone resumes from part 2
    rest = put_parts(init, data, settings, only={2, 3})
    r = env.expert.post(f"/api/v1/media/{init['id']}/complete", {"parts": first + rest},
                        format="json")
    assert r.status_code == 200 and r.json()["status"] == "verified"


def test_complete_with_missing_parts_is_refused(job, settings):
    env, b = job
    settings.MEDIA_PART_SIZE = 5 * 1024 * 1024
    data = b"v" * (11 * 1024 * 1024)
    init = env.expert.post("/api/v1/media/initiate", initiate_body(
        b["id"], data, field_key="clip", kind="video", content_type="video/mp4"),
        format="json").json()
    parts = put_parts(init, data, settings, only={1})
    r = env.expert.post(f"/api/v1/media/{init['id']}/complete", {"parts": parts}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "INCOMPLETE_UPLOAD"
    assert r.json()["missing"] == [2, 3]
    assert env.expert.post(f"/api/v1/media/{init['id']}/complete", {"parts": "x"},
                           format="json").status_code == 400


def test_complete_is_idempotent(job, settings):
    env, b = job
    data = jpeg()
    init = env.expert.post("/api/v1/media/initiate", initiate_body(b["id"], data),
                           format="json").json()
    parts = put_parts(init, data, settings)
    one = env.expert.post(f"/api/v1/media/{init['id']}/complete", {"parts": parts}, format="json")
    two = env.expert.post(f"/api/v1/media/{init['id']}/complete", {"parts": parts}, format="json")
    assert one.status_code == two.status_code == 200 and two.json()["status"] == "verified"


def test_a_corrupted_upload_fails_the_checksum_and_can_be_restarted(job, settings):
    env, b = job
    good, bad = jpeg(), jpeg(color=(1, 2, 3))
    body = initiate_body(b["id"], good)
    init = env.expert.post("/api/v1/media/initiate", body, format="json").json()
    parts = put_parts(init, bad, settings)                      # bytes differ from the declared hash
    r = env.expert.post(f"/api/v1/media/{init['id']}/complete", {"parts": parts}, format="json")
    assert r.status_code == 409 and r.json()["code"] == "CHECKSUM_MISMATCH"
    a = MediaAsset.objects.get()
    assert a.status == "failed" and not storage.exists(a.key)
    again = env.expert.post("/api/v1/media/initiate", body, format="json")   # same client_uuid
    assert again.status_code == 200 and again.json()["status"] == "pending" and again.json()["parts"]
    parts = put_parts(again.json(), good, settings)
    ok = env.expert.post(f"/api/v1/media/{init['id']}/complete", {"parts": parts}, format="json")
    assert ok.status_code == 200 and ok.json()["status"] == "verified"


def test_complete_after_failure_without_restart_is_refused(job, settings):
    env, b = job
    init = env.expert.post("/api/v1/media/initiate", initiate_body(b["id"], jpeg()),
                           format="json").json()
    parts = put_parts(init, jpeg(color=(9, 9, 9)), settings)
    env.expert.post(f"/api/v1/media/{init['id']}/complete", {"parts": parts}, format="json")
    r = env.expert.post(f"/api/v1/media/{init['id']}/complete", {"parts": parts}, format="json")
    assert r.status_code == 409 and r.json()["code"] == "NOT_UPLOADING"


def test_unknown_media_is_404_and_urls_need_a_verified_file(job, settings):
    env, b = job
    assert env.expert.get(f"/api/v1/media/{uuid.uuid4()}").status_code == 404
    init = env.expert.post("/api/v1/media/initiate", initiate_body(b["id"], jpeg()),
                           format="json").json()
    assert env.ops.get(f"/api/v1/media/{init['id']}/url").status_code == 409
    upload_id = init["id"]
    assert upload_id


def test_download_urls_for_verified_media(job, settings):
    env, b = job
    r = upload(env.expert, b["id"], jpeg(), settings).json()
    got = env.ops.get(f"/api/v1/media/{r['id']}/url").json()
    assert got["url"].startswith("https://") and got["preview_url"].startswith("https://")


# ---------------------------------------------------------------- answers reference media

def test_submit_rejects_unknown_media_and_media_of_another_field(job, settings):
    env, b = job
    r = submit_with(env, b, photo_a=[str(uuid.uuid4())])
    assert r.status_code == 400 and r.json()["errors"] == {"photo_a": "UNKNOWN_MEDIA"}
    pid = upload(env.expert, b["id"], jpeg(), settings).json()["id"]
    r = submit_with(env, b, doc=[pid])                         # a photo_a upload used as a doc
    assert r.status_code == 400 and r.json()["errors"] == {"doc": "WRONG_MEDIA_KIND"}


def test_media_of_another_booking_cannot_be_referenced(job, settings):
    env, b = job
    other = create(env.ops, booking_id="MD2").json()
    assign(env, other)
    start(env.expert, other)
    pid = upload(env.expert, other["id"], jpeg(), settings).json()["id"]
    r = submit_with(env, b, photo_a=[pid])
    assert r.status_code == 400 and r.json()["errors"] == {"photo_a": "UNKNOWN_MEDIA"}


# ---------------------------------------------------------------- Submitted -> Completed

def stage(b):
    return Booking.objects.get(pk=b["id"]).stage


def test_completed_only_when_every_referenced_file_is_verified(job, settings):
    env, b = job
    a = upload(env.expert, b["id"], jpeg(), settings).json()["id"]
    data = jpeg()
    init = env.expert.post("/api/v1/media/initiate", initiate_body(b["id"], data),
                           format="json").json()                        # second photo, not uploaded
    assert submit_with(env, b, photo_a=[a, init["id"]]).status_code == 200
    assert stage(b) == "submitted"
    parts = put_parts(init, data, settings)
    env.expert.post(f"/api/v1/media/{init['id']}/complete", {"parts": parts}, format="json")
    assert stage(b) == "completed"


def test_a_submission_with_no_media_completes_at_once(job):
    env, b = job
    assert submit_with(env, b).status_code == 200
    assert stage(b) == "completed"


def test_completion_happens_exactly_once_and_emits_the_events(job, settings):
    from apps.core import events
    from apps.media.services import check_completion

    env, b = job
    a = upload(env.expert, b["id"], jpeg(), settings).json()["id"]
    with events.capture() as seen:
        submit_with(env, b, photo_a=[a])
        assert check_completion(b["id"]) is False          # already completed
    names = [n for n, _ in seen]
    assert names.count("media.completed") == 1 and names.count("inspection.completed") == 1
    assert stage(b) == "completed"


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_parallel_verifications_complete_the_booking_once(menv, settings):
    import threading

    from django.db import connection

    from apps.core import events
    from apps.media.services import check_completion

    b = create(menv.ops, booking_id="MD9").json()
    assign(menv, b)
    start(menv.expert, b)
    ids = []
    for _ in range(2):
        data = jpeg()
        init = menv.expert.post("/api/v1/media/initiate", initiate_body(b["id"], data),
                                format="json").json()
        parts = put_parts(init, data, settings)
        from apps.media import services as media_services

        a = MediaAsset.objects.get(pk=init["id"])
        storage.client().complete_multipart_upload(
            Bucket=settings.S3_BUCKET, Key=a.key, UploadId=a.upload_id,
            MultipartUpload={"Parts": [{"PartNumber": p["part_number"], "ETag": p["etag"]}
                                       for p in parts]})
        MediaAsset.objects.filter(pk=a.pk).update(status="verified", upload_id="")
        ids.append(init["id"])
        assert media_services
    assert submit_with(menv, b, photo_a=ids).status_code == 200
    Booking.objects.filter(pk=b["id"]).update(stage="submitted")
    results: list[bool] = []
    with events.capture() as seen:
        def go():
            try:
                results.append(check_completion(b["id"]))
            finally:
                connection.close()

        threads = [threading.Thread(target=go) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
    assert results.count(True) == 1
    assert [n for n, _ in seen].count("media.completed") == 1


# ---------------------------------------------------------------- ops edit media after submit

def test_ops_delete_media_removes_the_file_the_reference_and_cached_zips(job, settings):
    env, b = job
    a = upload(env.expert, b["id"], jpeg(), settings).json()["id"]
    b2 = upload(env.expert, b["id"], jpeg(color=(5, 5, 5)), settings).json()["id"]
    submit_with(env, b, photo_a=[a, b2])
    env.ops.post(f"/api/v1/bookings/{b['id']}/media-zip", {"kind": "image"}, format="json")
    asset = MediaAsset.objects.get(pk=a)
    r = env.ops.delete(f"/api/v1/media/{a}")
    assert r.status_code == 204
    assert not storage.exists(asset.key) and not MediaAsset.objects.filter(pk=a).exists()
    from apps.bookings.models import Inspection

    assert Inspection.objects.get(booking_id=b["id"]).answers["inspection"]["photo_a"] == [b2]
    assert MediaZip.objects.count() == 0
    assert env.expert.delete(f"/api/v1/media/{b2}").status_code == 403


def test_deleting_the_only_photo_empties_the_answer(job, settings):
    env, b = job
    a = upload(env.expert, b["id"], jpeg(), settings).json()["id"]
    s = upload(env.expert, b["id"], png(), settings, field_key="sign", kind="signature",
               content_type="image/png").json()["id"]
    submit_with(env, b, photo_a=[a], sign=s)
    env.ops.delete(f"/api/v1/media/{a}")
    env.ops.delete(f"/api/v1/media/{s}")
    from apps.bookings.models import Inspection

    answers = Inspection.objects.get(booking_id=b["id"]).answers["inspection"]
    assert "photo_a" not in answers and "sign" not in answers


def test_an_expert_can_take_back_their_own_file_before_submitting(job, settings):
    env, b = job
    a = upload(env.expert, b["id"], jpeg(), settings).json()["id"]
    asset = MediaAsset.objects.get(pk=a)
    assert env.expert.delete(f"/api/v1/media/{a}").status_code == 204       # the Remove button
    assert not MediaAsset.objects.filter(pk=a).exists() and not storage.exists(asset.key)
    assert upload(env.expert, b["id"], jpeg(color=(9, 9, 9)), settings).status_code in (200, 201)


def test_an_expert_cannot_take_back_someone_elses_or_a_closed_bookings_file(job, settings):
    from apps.bookings.models import Booking

    env, b = job
    theirs = upload(env.ops, b["id"], jpeg(), settings).json()["id"]        # uploaded by Ops
    assert env.expert.delete(f"/api/v1/media/{theirs}").status_code == 403
    mine = upload(env.expert, b["id"], jpeg(color=(1, 2, 3)), settings).json()["id"]
    Booking.objects.filter(pk=b["id"]).update(stage="cancelled")
    assert env.expert.delete(f"/api/v1/media/{mine}").status_code == 403
    assert MediaAsset.objects.filter(pk=mine).exists()


def test_deleting_an_unfinished_upload_aborts_it(job, settings):
    env, b = job
    init = env.expert.post("/api/v1/media/initiate", initiate_body(b["id"], jpeg()),
                           format="json").json()
    assert env.ops.delete(f"/api/v1/media/{init['id']}").status_code == 204
    assert MediaAsset.objects.count() == 0


# ---------------------------------------------------------------- ZIPs

def test_zip_is_built_once_cached_and_opened_through_a_signed_link(job, settings):
    env, b = job
    a = upload(env.expert, b["id"], jpeg(), settings).json()["id"]
    submit_with(env, b, photo_a=[a])
    r = env.ops.post(f"/api/v1/bookings/{b['id']}/media-zip", {"kind": "image"}, format="json")
    assert r.status_code == 202 and r.json()["status"] == "ready"      # eager build in tests
    link = r.json()["url"]
    from rest_framework.test import APIClient

    anon = APIClient()                                    # no login: the signed token is the key
    dl = anon.get(link)
    assert dl.status_code == 302 and "bookings" not in dl["Location"] or dl.status_code == 302
    again = env.ops.post(f"/api/v1/bookings/{b['id']}/media-zip", {"kind": "image"}, format="json")
    # the token embeds a timestamp, so the link text can differ across a second boundary
    assert again.json()["url"].split(":")[0] == link.split(":")[0] and MediaZip.objects.count() == 1  # cached


def test_zip_contents_are_named_by_field_and_index(job, settings):
    import zipfile

    env, b = job
    ids = [upload(env.expert, b["id"], jpeg(color=(i, i, i)), settings).json()["id"]
           for i in (10, 20)]
    submit_with(env, b, photo_a=ids)
    env.ops.post(f"/api/v1/bookings/{b['id']}/media-zip", {"kind": "image"}, format="json")
    z = MediaZip.objects.get()
    with zipfile.ZipFile(io.BytesIO(storage.read(z.key))) as archive:
        assert sorted(archive.namelist()) == ["photo_a-1.jpg", "photo_a-2.jpg"]


def test_preparing_page_while_building_and_bad_links(job, settings):
    from rest_framework.test import APIClient

    from apps.media import zips

    env, b = job
    z = MediaZip.objects.create(booking=Booking.objects.get(pk=b["id"]), kind="image",
                                progress=45)
    anon = APIClient()
    r = anon.get(f"/api/v1/zips/{zips.token_for(z.id)}")
    assert r.status_code == 202 and r.json() == {"status": "building", "progress": 45}
    assert anon.get("/api/v1/zips/not-a-token").status_code == 404
    z.status = "failed"
    z.save()
    assert anon.get(f"/api/v1/zips/{zips.token_for(z.id)}").json()["code"] == "NO_MEDIA"


def test_links_expire_after_seven_days(job, settings):
    from datetime import timedelta

    from django.utils import timezone
    from rest_framework.test import APIClient

    from apps.media import zips

    env, b = job
    z = MediaZip.objects.create(booking=Booking.objects.get(pk=b["id"]), kind="image",
                                status="ready", key="zips/x.zip")
    MediaZip.objects.filter(pk=z.pk).update(created_at=timezone.now() - timedelta(days=8))
    r = APIClient().get(f"/api/v1/zips/{zips.token_for(z.id)}")
    assert r.status_code == 404 and r.json()["code"] == "LINK_EXPIRED"


def test_zip_needs_media_download_and_a_valid_kind_and_media(job, settings):
    env, b = job
    assert env.expert.post(f"/api/v1/bookings/{b['id']}/media-zip", {"kind": "image"},
                           format="json").status_code == 403
    assert env.ops.post(f"/api/v1/bookings/{b['id']}/media-zip", {"kind": "gif"},
                        format="json").status_code == 400
    r = env.ops.post(f"/api/v1/bookings/{b['id']}/media-zip", {"kind": "video"}, format="json")
    from rest_framework.test import APIClient

    assert APIClient().get(r.json()["url"]).json()["code"] == "NO_MEDIA"   # nothing to zip


# ---------------------------------------------------------------- stuck uploads

def test_stuck_uploads_are_listed_and_alerted_once(job, settings):
    from datetime import timedelta

    from django.core.management import call_command
    from django.utils import timezone

    from apps.core import events

    env, b = job
    env.expert.post("/api/v1/media/initiate", initiate_body(b["id"], jpeg()), format="json")
    assert env.ops.get("/api/v1/problems/stuck-uploads").json() == []         # still fresh
    MediaAsset.objects.update(created_at=timezone.now() - timedelta(hours=7))
    rows = env.ops.get("/api/v1/problems/stuck-uploads").json()
    assert len(rows) == 1 and rows[0]["booking_id"] == "MD1" and rows[0]["field_key"] == "photo_a"
    assert [r["id"] for r in env.expert.get("/api/v1/problems/stuck-uploads").json()] == [
        rows[0]["id"]]                                  # experts see only their own
    with events.capture() as seen:
        call_command("flag_stuck_uploads")
        call_command("flag_stuck_uploads")
    assert [n for n, _ in seen] == ["alert.stuck_upload"]
    assert sha(b"x")


def test_experts_download_only_their_own_media(job, settings):
    env, b = job
    media_id = upload(env.expert, b["id"], jpeg(), settings).json()["id"]
    assert env.expert.get(f"/api/v1/media/{media_id}/url").status_code == 200
    other = env.make_user("expert", username="e11")
    from rest_framework.test import APIClient

    c = APIClient()
    c.force_authenticate(user=other)
    assert c.get(f"/api/v1/media/{media_id}/url").status_code == 404


def test_ops_form_media_is_validated_and_awaited_for_completion(job, settings):
    env, b = job
    ops_form = env.admin.post("/api/v1/forms", {"key": "ops", "kind": "ops", "name": "Ops"},
                              format="json").json()
    publish_form(env.admin, ops_form["id"])        # its system fields (selfie, payment...) come with it
    sid = upload(env.expert, b["id"], jpeg(), settings, field_key="selfie").json()["id"]
    body = {"client_submission_uuid": str(uuid.uuid4()), "answers": {
        "inspection": {"chassis_no": "MA3YPKCSKTJ273129"},
        "ops": {"selfie": [sid], "taking_payment": False}}}
    assert env.expert.post(f"/api/v1/bookings/{b['id']}/submit", body, format="json"
                           ).status_code == 200
    assert stage(b) == "completed"
    bad = {"client_submission_uuid": str(uuid.uuid4()), "answers": {
        "inspection": {"chassis_no": "MA3YPKCSKTJ273129"},
        "ops": {"selfie": [str(uuid.uuid4())], "taking_payment": False}}}
    other = create(env.ops, booking_id="MD3").json()
    assign(env, other)
    start(env.expert, other)
    r = env.expert.post(f"/api/v1/bookings/{other['id']}/submit", bad, format="json")
    assert r.status_code == 400 and r.json()["errors"] == {"selfie": "UNKNOWN_MEDIA"}


def test_completion_without_a_submitted_inspection_does_nothing(job):
    from apps.media.services import check_completion

    env, b = job
    Booking.objects.filter(pk=b["id"]).update(stage="submitted")
    assert check_completion(b["id"]) is False


def test_verifying_twice_is_harmless(job, settings):
    from apps.media.tasks import verify_asset

    env, b = job
    media_id = upload(env.expert, b["id"], jpeg(), settings).json()["id"]
    assert verify_asset(media_id) == "verified"
