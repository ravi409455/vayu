"""Plan batch 5: deleted and expired files leave storage (H-02, F-069, F-081, R-18, F-121)."""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.bookings.models import Booking
from apps.core import app_settings
from apps.media import storage
from apps.media.models import MediaAsset, MediaZip
from apps.media.tasks import purge_expired
from apps.media.tests.conftest import jpeg, upload
from apps.media.tests.test_upload import job, menv, submit_with  # noqa: F401
from apps.reports.models import Report
from apps.reports.render import print_keys

pytestmark = pytest.mark.django_db


def _files(env, b, settings, field="photo_a", kind="photo"):
    a = MediaAsset.objects.get(pk=upload(env.expert, b["id"], jpeg(), settings,
                                         field_key=field, kind=kind).json()["id"])
    for k in print_keys(a.id):
        storage.put(k, b"print", "image/jpeg")
    return a


def test_deleting_a_booking_removes_every_file_it_had(job, settings):
    env, b = job
    a = _files(env, b, settings)
    storage.put("reports/x/rev1.pdf", b"%PDF", "application/pdf")
    Report.objects.create(booking_id=b["id"], key="reports/x/rev1.pdf", status="ready")
    storage.put("zips/z.zip", b"PK", "application/zip")
    MediaZip.objects.create(booking_id=b["id"], kind="photo", key="zips/z.zip", status="ready")
    keys = [a.key, a.preview_key, *print_keys(a.id), "reports/x/rev1.pdf", "zips/z.zip"]
    assert all(storage.exists(k) for k in keys)
    assert env.admin.delete(f"/api/v1/bookings/{b['id']}").status_code == 204
    assert not Booking.objects.filter(pk=b["id"]).exists()
    assert not any(storage.exists(k) for k in keys)


def test_a_refused_delete_removes_nothing(job, settings):
    env, b = job
    a = _files(env, b, settings)
    assert env.ops.delete(f"/api/v1/bookings/{b['id']}").status_code == 403
    assert storage.exists(a.key)


def test_removing_a_file_removes_its_print_copies_and_stale_zip_objects(job, settings):
    env, b = job
    a = _files(env, b, settings)
    storage.put("zips/old.zip", b"PK", "application/zip")
    MediaZip.objects.create(booking_id=b["id"], kind="photo", key="zips/old.zip", status="ready")
    assert env.expert.delete(f"/api/v1/media/{a.id}").status_code == 204
    assert not any(storage.exists(k) for k in [a.key, *print_keys(a.id), "zips/old.zip"])


def test_zips_past_their_seven_days_are_removed_by_the_hourly_purge(job, settings):
    env, b = job
    storage.put("zips/a.zip", b"PK", "application/zip")
    storage.put("zips/b.zip", b"PK", "application/zip")
    old = MediaZip.objects.create(booking_id=b["id"], kind="photo", key="zips/a.zip")
    MediaZip.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=8))
    MediaZip.objects.create(booking_id=b["id"], kind="video", key="zips/b.zip")
    purge_expired()
    assert not storage.exists("zips/a.zip") and storage.exists("zips/b.zip")
    assert list(MediaZip.objects.values_list("key", flat=True)) == ["zips/b.zip"]


def test_retention_covers_documents_signatures_and_cancelled_jobs(job, settings):
    env, b = job
    doc = _files(env, b, settings, field="doc", kind="file")
    photo = _files(env, b, settings)
    app_settings.put("media", {"photo_days": 30, "video_days": 0})
    MediaAsset.objects.update(created_at=timezone.now() - timedelta(days=40))
    Booking.objects.filter(pk=b["id"]).update(stage="cancelled",
                                              cancelled_at=timezone.now() - timedelta(days=5))
    assert purge_expired() == 0                          # cancelled 5 days ago: kept
    Booking.objects.filter(pk=b["id"]).update(cancelled_at=timezone.now() - timedelta(days=31))
    assert purge_expired() == 2
    for a in (doc, photo):
        a.refresh_from_db()
        assert a.status == "purged" and not storage.exists(a.key)
        assert not any(storage.exists(k) for k in print_keys(a.id))


def test_a_zip_whose_build_fails_is_shown_failed_and_made_again(job, settings, logged, caplog):
    """F-080 / F-108."""
    from unittest import mock

    from apps.media import zips

    env, b = job
    a = _files(env, b, settings)
    with mock.patch.object(zips.storage, "upload_file", side_effect=OSError("R2 down")), \
            pytest.raises(OSError):
        zips.request_zip(Booking.objects.get(pk=b["id"]), "photo", only=[str(a.id)])
    assert MediaZip.objects.get().status == "failed"
    again = zips.request_zip(Booking.objects.get(pk=b["id"]), "photo", only=[str(a.id)])
    assert again.status == "ready" and MediaZip.objects.count() == 2
    assert [getattr(r, "event", "") for r in caplog.records].count("zip.failed") == 1
    built = logged("zip.built")[0]
    assert (built["zip"], built["files"]) == (str(again.id), 1) and built["size"] > 0


def test_a_build_abandoned_by_a_restart_counts_as_failed(job):
    from apps.media import zips

    env, b = job
    z = MediaZip.objects.create(booking_id=b["id"], kind="photo")          # still "building"
    assert not zips.failed(z)
    MediaZip.objects.filter(pk=z.pk).update(created_at=timezone.now() - timedelta(minutes=31))
    z.refresh_from_db()
    assert zips.failed(z)


def test_why_a_file_failed_is_in_the_logs_with_its_booking(job, settings, caplog):
    """F-212."""
    import logging

    from apps.media.tests.conftest import initiate_body, put_parts

    env, b = job
    init = env.expert.post("/api/v1/media/initiate", initiate_body(b["id"], jpeg()),
                           format="json").json()
    parts = put_parts(init, jpeg(color=(1, 2, 3)), settings)
    with caplog.at_level(logging.WARNING, logger="vayu.events"):
        env.expert.post(f"/api/v1/media/{init['id']}/complete", {"parts": parts}, format="json")
    (rec,) = [r for r in caplog.records if r.message == "upload.failed"]
    assert rec.booking == b["id"] and rec.reason == "checksum"


def test_a_task_logs_with_the_request_id_that_queued_it():
    from types import SimpleNamespace

    from apps.core.logging import request_id_var
    from vayu.celery import _carry_request_id, _restore_request_id

    request_id_var.set("req-42")
    headers: dict = {}
    _carry_request_id(headers=headers)
    assert headers == {"request_id": "req-42"}
    _carry_request_id(headers=None)                                     # nothing to carry it in
    request_id_var.set("-")
    _restore_request_id(task=SimpleNamespace(request=SimpleNamespace(request_id="req-42")),
                        task_id="task-7")
    assert request_id_var.get() == "req-42"
    from apps.core.logging import task_id_var

    assert task_id_var.get() == "task-7"                     # every worker line names its task
    _restore_request_id(task=SimpleNamespace(request=SimpleNamespace()))
    assert request_id_var.get() == "-"


def test_a_check_running_when_its_booking_is_deleted_leaves_no_files_behind(job, settings):
    """Review: verify_asset finishing after the booking (and its delete_files) went."""
    from unittest import mock

    from apps.media import tasks
    from apps.media.tests.conftest import initiate_body, put_parts

    env, b = job
    data = jpeg(4000, 3000)                                  # makes a preview and a copy
    init = env.expert.post("/api/v1/media/initiate", initiate_body(b["id"], data),
                           format="json").json()
    parts = put_parts(init, data, settings)
    a = MediaAsset.objects.get(pk=init["id"])
    storage.complete_multipart(a.key, a.upload_id, parts)
    MediaAsset.objects.filter(pk=a.pk).update(status="uploaded", upload_id="")
    real = tasks._check

    def delete_meanwhile(asset):
        ok = real(asset)
        Booking.objects.filter(pk=b["id"]).delete()          # the Admin deletes it now
        return ok

    with mock.patch.object(tasks, "_check", side_effect=delete_meanwhile):
        assert tasks.verify_asset(str(a.pk)) == "gone"
    assert not any(storage.exists(k) for k in (a.key, f"previews/{a.pk}.jpg",
                                               f"copies/{a.pk}.jpg"))
    assert tasks.verify_asset(str(a.pk)) == "gone"            # a retry after that: nothing


def test_a_zip_built_while_its_booking_is_deleted_is_removed(job, settings):
    from unittest import mock

    from apps.media import zips

    env, b = job
    a = _files(env, b, settings)
    real = zips.storage.upload_file

    def upload_then_delete(path, key, ctype):
        real(path, key, ctype)
        Booking.objects.filter(pk=b["id"]).delete()
        return None

    with mock.patch.object(zips.storage, "upload_file", side_effect=upload_then_delete):
        zips.request_zip(Booking.objects.get(pk=b["id"]), "photo", only=[str(a.id)])
    assert not [k for k in storage.client().list_objects_v2(
        Bucket=settings.S3_BUCKET, Prefix="zips/").get("Contents", [])]


def test_failed_attempts_are_counted_across_retries(job, settings):
    """F-247: a retry reuses the row; the failures are not forgotten."""
    from apps.media.tests.conftest import initiate_body, put_parts

    env, b = job
    body = initiate_body(b["id"], jpeg())
    for n in (1, 2):
        init = env.expert.post("/api/v1/media/initiate", body, format="json").json()
        parts = put_parts(init, jpeg(color=(n, 2, 3)), settings)           # wrong bytes
        env.expert.post(f"/api/v1/media/{init['id']}/complete", {"parts": parts}, format="json")
        assert MediaAsset.objects.get(pk=init["id"]).failed_attempts == n
