"""Ops finish a job whose expert's files never arrive (owner, 2026-11-24): only once every required
field has its file; missing optional ones are left out and added later if they arrive."""
from unittest import mock

import pytest

from apps.bookings.models import Booking, BookingActivity
from apps.forms.models import Field
from apps.media.tests.conftest import initiate_body, jpeg, upload
from apps.media.tests.test_upload import job, menv, submit_with  # noqa: F401

pytestmark = pytest.mark.django_db


def stuck(env, b, n=1):
    """The expert registered n photos and submitted, but the files never finish uploading."""
    ids = [env.expert.post("/api/v1/media/initiate", initiate_body(b["id"], jpeg(color=(i, 1, 1))),
                           format="json").json()["id"] for i in range(n)]
    assert submit_with(env, b, photo_a=ids).status_code == 200
    assert Booking.objects.get(pk=b["id"]).stage == "submitted"
    return ids


def test_missing_optional_files_can_be_finished_without(job, settings):
    env, b = job
    stuck(env, b, 2)
    r = env.ops.get(f"/api/v1/bookings/{b['id']}/missing-files").json()
    assert r == {"can_finish": True, "missing": [{"part": "inspection", "key": "photo_a",
                 "label": "photo_a", "count": 2, "required": False}]}
    assert env.expert.post(f"/api/v1/bookings/{b['id']}/finish").status_code == 403   # Ops only
    with mock.patch("apps.reports.tasks.render_report.delay") as render:
        r = env.ops.post(f"/api/v1/bookings/{b['id']}/finish")
    assert r.status_code == 200 and r.json() == {"stage": "completed"}
    render.assert_called_once_with(b["id"])                               # the report is made now
    row = BookingActivity.objects.get(kind="finished_without_files")
    assert row.changes == {"stage": ["submitted", "completed"], "missing": 2}
    assert row.keys == ["inspection.photo_a", "stage"]
    assert env.ops.post(f"/api/v1/bookings/{b['id']}/finish").status_code == 409     # once only


def test_a_required_field_needs_its_file_from_ops_first(job, settings):
    env, b = job
    Field.objects.filter(key="photo_a").update(required=True)
    [old] = stuck(env, b)
    r = env.ops.get(f"/api/v1/bookings/{b['id']}/missing-files").json()
    assert r["can_finish"] is False and r["missing"][0]["required"] is True
    r = env.ops.post(f"/api/v1/bookings/{b['id']}/finish")
    assert r.status_code == 409 and r.json()["code"] == "REQUIRED_FILES_MISSING"
    assert r.json()["keys"] == ["inspection.photo_a"]
    new = upload(env.ops, b["id"], jpeg(color=(9, 9, 9)), settings, source="gallery",
                 replaces=old).json()["id"]
    assert env.ops.post(f"/api/v1/media/{new}/attach", {"replaces": old}, format="json").status_code == 204
    # Ops' file was the only one missing: the job completes by itself, nothing left to finish
    assert Booking.objects.get(pk=b["id"]).stage == "completed"
    assert env.ops.get(f"/api/v1/bookings/{b['id']}/missing-files").json() == {
        "missing": [], "can_finish": False}


def test_nothing_missing_or_not_waiting_for_files(job, settings):
    env, b = job
    assert env.ops.get(f"/api/v1/bookings/{b['id']}/missing-files").json()["missing"] == []
    r = env.ops.post(f"/api/v1/bookings/{b['id']}/finish")
    assert r.status_code == 409 and r.json()["code"] == "INVALID_STAGE"


def test_an_ops_add_takes_the_place_of_a_file_that_never_arrived(job, settings):
    env, b = job
    Field.objects.filter(key="photo_a").update(required=True, config={"max_count": 1})
    [old] = stuck(env, b)
    r = upload(env.ops, b["id"], jpeg(color=(5, 5, 5)), settings, source="gallery")   # plain Add
    assert r.status_code == 200, r.json()
    new = r.json()["id"]
    assert env.ops.post(f"/api/v1/media/{new}/attach", {}, format="json").status_code == 204
    from apps.bookings.models import Inspection
    assert Inspection.objects.get(booking_id=b["id"]).answers["inspection"]["photo_a"] == [new]
    assert BookingActivity.objects.filter(kind="media_replaced").exists()     # kept as history
    assert Booking.objects.get(pk=b["id"]).stage == "completed"              # nothing left missing
    assert old != new


def test_with_room_left_an_ops_add_is_just_added(job, settings):
    env, b = job
    [mine] = stuck(env, b)                                   # photo_a takes 2: one place left
    new = upload(env.ops, b["id"], jpeg(color=(6, 6, 6)), settings, source="gallery").json()["id"]
    assert env.ops.post(f"/api/v1/media/{new}/attach", {}, format="json").status_code == 204
    from apps.bookings.models import Inspection
    assert Inspection.objects.get(booking_id=b["id"]).answers["inspection"]["photo_a"] == [mine, new]


def test_only_a_file_that_never_arrived_on_a_waiting_job_is_taken_over(job, settings):
    from apps.media.models import MediaAsset
    from apps.media.services import unarrived
    env, b = job
    [old] = stuck(env, b)
    booking = Booking.objects.get(pk=b["id"])
    assert unarrived(booking, [old]) == [old]
    MediaAsset.objects.filter(pk=old).update(status="purged")         # arrived once, purged later
    assert unarrived(booking, [old]) == []
    MediaAsset.objects.filter(pk=old).update(status="pending")
    Booking.objects.filter(pk=b["id"]).update(stage="completed")      # no longer waiting
    assert unarrived(Booking.objects.get(pk=b["id"]), [old]) == []
