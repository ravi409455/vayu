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
