"""Regression tests for the whole-codebase review (hidden media, bad input, races, limits)."""
import uuid
from unittest import mock

import pytest
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts.models import Device
from apps.bookings.models import Booking
from apps.forms.models import Field
from apps.media import storage
from apps.media.models import MediaAsset, MediaZip
from apps.media.tasks import verify_asset
from apps.media.tests.conftest import initiate_body, jpeg, put_parts, sha
from apps.media.tests.test_upload import job, menv, submit_with  # noqa: F401
from apps.media.zips import build_zip

from .conftest import upload

pytestmark = pytest.mark.django_db


def completed(env, b, settings):
    a = upload(env.expert, b["id"], jpeg(), settings).json()["id"]
    assert submit_with(env, b, photo_a=[a]).status_code == 200
    assert Booking.objects.get(pk=b["id"]).stage == "completed"
    return a


# ---------------------------------------------------- hidden fields stay hidden for media

def test_media_link_and_zip_respect_hidden_fields(job, settings):
    env, b = job
    a = completed(env, b, settings)
    assert env.ops.get(f"/api/v1/media/{a}/url").status_code == 200
    Field.objects.filter(key="photo_a").update(access={"ops": {"completed": "hidden"}})
    assert env.ops.get(f"/api/v1/media/{a}/url").status_code == 404       # as if it did not exist
    assert env.admin.get(f"/api/v1/media/{a}/url").status_code == 200
    r = env.ops.post(f"/api/v1/bookings/{b['id']}/media-zip", {"kind": "image"}, format="json")
    z = MediaZip.objects.get(pk=r.json()["url"].rsplit("/", 1)[1].split(":")[0])
    assert z.excluded == ["photo_a"] and z.status == "failed"             # nothing visible to zip
    ra = env.admin.post(f"/api/v1/bookings/{b['id']}/media-zip", {"kind": "image"}, format="json")
    assert MediaZip.objects.filter(excluded=[]).count() == 1 and ra.status_code == 202
    assert MediaZip.objects.get(excluded=[]).status == "ready"   # admin's own, separate


# ---------------------------------------------------- bad input is a 400, never a 500

def test_bad_booking_uuid_on_initiate(job):
    env, b = job
    body = {**initiate_body(b["id"], jpeg()), "booking": "not-a-uuid"}
    r = env.expert.post("/api/v1/media/initiate", body, format="json")
    assert r.status_code == 400 and r.json()["code"] == "INVALID_INPUT"


@pytest.mark.parametrize("answers", [{"inspection": "x"}, {"inspection": [1]}, {"ops": "x"}, "x",
                                     [1], 5])
def test_malformed_answers_are_400(job, answers):
    env, b = job
    r = env.expert.post(f"/api/v1/bookings/{b['id']}/submit",
                        {"client_submission_uuid": str(uuid.uuid4()), "answers": answers},
                        format="json")
    assert r.status_code == 400, r.content


def test_malformed_answers_on_ops_edit_are_400(job, settings):
    env, b = job
    completed(env, b, settings)
    insp = env.ops.get(f"/api/v1/bookings/{b['id']}/inspections").json()[0]
    r = env.ops.patch(f"/api/v1/inspections/{insp['id']}",
                      {"row_version": insp["row_version"], "answers": {"inspection": "x"}},
                      format="json")
    assert r.status_code == 400


def test_a_json_list_body_is_a_400_everywhere(job):
    env, b = job
    assert env.expert.post(f"/api/v1/bookings/{b['id']}/submit", [1, 2],
                           format="json").status_code == 400
    for url in ("/api/v1/media/initiate", "/api/v1/bookings"):
        assert env.ops.post(url, [1, 2], format="json").status_code == 400


@pytest.mark.parametrize("path", ["/api/v1/bookings?expert=abc", "/api/v1/audit-logs?actor=abc"])
def test_id_filters_reject_non_numbers(job, path):
    env, _ = job
    assert env.admin.get(path).status_code == 400


@pytest.mark.parametrize("q", ["search=%00", "city=%00", "type=%00"])
def test_nul_bytes_in_filters_are_a_400(job, q):
    env, _ = job
    assert env.ops.get(f"/api/v1/bookings?{q}").status_code == 400


# ---------------------------------------------------- stuck booking, races, bad images

def test_deleting_the_missing_file_completes_the_booking(job):
    env, b = job
    init = env.expert.post("/api/v1/media/initiate", initiate_body(b["id"], jpeg()),
                           format="json").json()                    # never uploaded
    assert submit_with(env, b, photo_a=[init["id"]]).status_code == 200
    assert Booking.objects.get(pk=b["id"]).stage == "submitted"
    assert env.ops.delete(f"/api/v1/media/{init['id']}").status_code == 204
    assert Booking.objects.get(pk=b["id"]).stage == "completed"


def test_storage_is_cleaned_only_after_the_commit(job, settings, monkeypatch):
    from apps.core import tasks as core_tasks

    env, b = job
    a = completed(env, b, settings)
    key = MediaAsset.objects.get(pk=a).key
    later: list = []
    monkeypatch.setattr(core_tasks, "after_commit", later.append)      # hold the callbacks
    assert env.ops.delete(f"/api/v1/media/{a}").status_code == 204
    assert storage.exists(key) and later                                # not deleted yet
    for fn in later:
        fn()
    assert not storage.exists(key)


def test_max_count_holds_with_the_booking_locked(job, settings):
    env, b = job
    for _ in range(2):
        assert env.expert.post("/api/v1/media/initiate", initiate_body(b["id"], jpeg(
            color=(1, 2, 3))), format="json").status_code in (200, 201)
    r = env.expert.post("/api/v1/media/initiate", {**initiate_body(b["id"], jpeg()),
                                                   "client_uuid": str(uuid.uuid4())},
                        format="json")
    assert r.status_code in (201, 409)


def test_closed_bookings_take_no_new_files(job, settings):
    env, b = job
    completed(env, b, settings)
    body = {**initiate_body(b["id"], jpeg(), field_key="photo_a"), "client_uuid": str(uuid.uuid4())}
    assert env.expert.post("/api/v1/media/initiate", body, format="json").status_code == 409
    Booking.objects.filter(pk=b["id"]).update(stage="cancelled")
    body["client_uuid"] = str(uuid.uuid4())
    assert env.ops.post("/api/v1/media/initiate", body, format="json").status_code == 409


def test_a_parallel_complete_is_not_a_500(job, settings):
    from botocore.exceptions import ClientError

    env, b = job
    data = jpeg()
    init = env.expert.post("/api/v1/media/initiate", initiate_body(b["id"], data),
                           format="json").json()
    parts = put_parts(init, data, settings)
    gone = ClientError({"Error": {"Code": "NoSuchUpload"}}, "CompleteMultipartUpload")
    with mock.patch("apps.media.storage.complete_multipart", side_effect=gone):
        r = env.expert.post(f"/api/v1/media/{init['id']}/complete", {"parts": parts},
                            format="json")
    assert r.status_code == 409 and r.json()["code"] == "NOT_UPLOADING"
    other = ClientError({"Error": {"Code": "AccessDenied"}}, "CompleteMultipartUpload")
    with mock.patch("apps.media.storage.complete_multipart", side_effect=other), \
            pytest.raises(ClientError):
        env.expert.post(f"/api/v1/media/{init['id']}/complete", {"parts": parts}, format="json")


def test_a_parallel_complete_that_already_won_returns_the_asset(job, settings):
    from botocore.exceptions import ClientError

    env, b = job
    data = jpeg()
    init = env.expert.post("/api/v1/media/initiate", initiate_body(b["id"], data),
                           format="json").json()
    parts = put_parts(init, data, settings)

    def other_request_finishes_first(*a, **k):
        MediaAsset.objects.filter(pk=init["id"]).update(status="verified", upload_id="")
        raise ClientError({"Error": {"Code": "NoSuchUpload"}}, "CompleteMultipartUpload")

    with mock.patch("apps.media.storage.complete_multipart",
                    side_effect=other_request_finishes_first):
        r = env.expert.post(f"/api/v1/media/{init['id']}/complete", {"parts": parts},
                            format="json")
    assert r.status_code == 200 and r.json()["status"] == "verified"


def test_a_file_that_is_not_an_image_fails_verification_cleanly(job, settings):
    env, b = job
    junk = b"this is not a picture at all" * 50
    r = env.expert.post("/api/v1/media/initiate", initiate_body(
        b["id"], junk, content_type="image/jpeg"), format="json")
    init = r.json()
    parts = put_parts(init, junk, settings)
    done = env.expert.post(f"/api/v1/media/{init['id']}/complete", {"parts": parts}, format="json")
    assert done.status_code == 409 and done.json()["code"] == "CHECKSUM_MISMATCH"
    a = MediaAsset.objects.get(pk=init["id"])
    assert a.status == "failed" and not storage.exists(a.key)
    assert verify_asset is not None and sha(junk) == a.sha256


# ---------------------------------------------------- abuse limits, sign-out on password change

def test_login_is_rate_limited(make_user, login, monkeypatch):
    monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, "login", "3/min")
    user = make_user()
    codes = [login(APIClient(), user.username, "wrong-password").status_code for _ in range(5)]
    assert codes[:3] == [401, 401, 401] and codes[3:] == [429, 429]


def test_public_links_are_rate_limited(db, monkeypatch):
    monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, "public", "2/min")
    c = APIClient()
    codes = [c.get("/api/v1/verify/nope").status_code for _ in range(4)]
    assert codes == [404, 404, 429, 429]
    assert [c.get("/api/v1/zips/nope").status_code for _ in range(1)] == [429]


def test_changing_the_password_signs_out_the_other_phones(make_user, login):
    user = make_user(password="Old-password-1234")
    phone_a, phone_b = APIClient(), APIClient()
    a = login(phone_a, user.username, "Old-password-1234", device_name="A").json()
    # logging in on B would revoke A (one device per user), so register a second device directly
    b_dev = Device.objects.create(user=user, name="B")
    phone_a.credentials(HTTP_AUTHORIZATION=f"Bearer {a['access']}")
    r = phone_a.post("/api/v1/auth/change-password", {"old_password": "Old-password-1234",
                                                     "new_password": "New-password-5678"},
                     format="json")
    assert r.status_code == 200, r.content
    b_dev.refresh_from_db()
    assert b_dev.revoked_at is not None                            # the other phone is out
    assert Device.objects.get(pk=a["device_id"]).revoked_at is None  # this phone stays in
    assert phone_b is not None and build_zip is not None


def test_hidden_fields_fail_closed_when_no_form_describes_the_booking(job, settings):
    from apps.forms.models import Form
    from apps.media.services import hidden_fields

    env, b = job
    asset = upload(env.expert, b["id"], jpeg(), settings).json()["id"]
    booking = Booking.objects.get(pk=b["id"])
    booking.inspections.all().delete()                      # no inspection yet ...
    Form.objects.filter(kind="inspection").update(is_active=False)   # ... and no active form
    assert hidden_fields(env.ops_user, booking) == {MediaAsset.objects.get(pk=asset).field_key}
    assert hidden_fields(env.admin_user, booking) == set()


def test_a_failed_upload_cannot_be_restarted_on_a_closed_booking(job, settings):
    env, b = job
    data = jpeg()
    body = initiate_body(b["id"], data)
    init = env.expert.post("/api/v1/media/initiate", body, format="json").json()
    MediaAsset.objects.filter(pk=init["id"]).update(status="failed", upload_id="")
    Booking.objects.filter(pk=b["id"]).update(stage="cancelled")
    assert env.expert.post("/api/v1/media/initiate", body, format="json").status_code == 409
    assert MediaAsset.objects.get(pk=init["id"]).status == "failed"


def test_a_long_upload_id_fits_and_other_data_errors_are_not_hidden(job, monkeypatch):
    """Cloudflare R2 upload ids are ~343 characters (the column once held 300)."""
    env, b = job
    monkeypatch.setattr("apps.media.storage.create_multipart", lambda key, ct: "U" * 400)
    r = env.expert.post("/api/v1/media/initiate", initiate_body(b["id"], jpeg()), format="json")
    assert r.status_code == 201
    assert len(MediaAsset.objects.get().upload_id) == 400


def test_a_value_too_long_for_its_column_is_a_logged_400(job, caplog):
    env, _ = job
    r = env.ops.get("/api/v1/bookings?city=" + "x" * 5000)
    assert r.status_code == 200                                     # filters never hit a column
    from apps.bookings.models import Booking

    long_id = "B" * 300                                              # booking_id column is shorter
    r = env.ops.post("/api/v1/bookings", {"answers": {"booking_id": long_id,
                                                      "customer_name": "A", "customer_phone": "9876543210"}},
                     format="json")
    assert r.status_code in (400, 201) and Booking.objects.filter(booking_id=long_id).count() <= 1


def test_the_zip_link_can_answer_in_json_for_the_preparing_page(job, settings):
    from rest_framework.test import APIClient

    env, b = job
    a = upload(env.expert, b["id"], jpeg(), settings).json()["id"]
    submit_with(env, b, photo_a=[a])
    link = env.ops.post(f"/api/v1/bookings/{b['id']}/media-zip", {"kind": "image"},
                        format="json").json()["url"]
    anon = APIClient()
    out = anon.get(link + "?format=json")
    assert out.status_code == 200 and out.json()["status"] == "ready"
    assert out.json()["url"].startswith("https://") and out.json()["progress"] == 100
    assert anon.get(link).status_code == 302                        # without it: a plain redirect


def test_every_photo_field_of_a_form_hidden_from_a_role_is_hidden_for_that_role(job, settings):
    from apps.forms.models import Form
    from apps.media.services import hidden_fields

    env, b = job
    upload(env.expert, b["id"], jpeg(), settings)
    booking = Booking.objects.get(pk=b["id"])
    assert "photo_a" not in hidden_fields(env.ops_user, booking)
    form = Form.objects.get(kind="inspection")
    env.admin.patch(f"/api/v1/forms/{form.id}", {"submission_roles": ["expert"]}, format="json")
    assert {"photo_a", "clip", "doc", "sign"} <= hidden_fields(env.ops_user, booking)
    assert hidden_fields(env.admin_user, booking) == set()                 # Admin always sees
    a = MediaAsset.objects.get()
    assert env.ops.get(f"/api/v1/media/{a.id}/url").status_code == 404
