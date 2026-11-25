"""Edge paths of uploads, Ops attach / remove, ZIP places and the retention purge that the main
media tests don't reach (they keep the apps.media 100% branch-coverage gate honest)."""
from typing import cast
from unittest import mock

import pytest

from apps.bookings.models import Inspection
from apps.core.errors import CodedError
from apps.forms.models import Field
from apps.media import services, tasks, zips
from apps.media.models import MediaAsset, MediaZip
from apps.media.tests.conftest import jpeg, upload
from apps.media.tests.test_ops_media import ops_upload, submitted
from apps.media.tests.test_upload import job, menv, submit_with  # noqa: F401

pytestmark = pytest.mark.django_db


def test_a_signature_field_takes_one_file_whatever_its_config():
    assert services.max_count(Field(type="signature", config={"max_count": 5})) == 1


def test_files_are_added_only_after_the_expert_submits(job):
    env, b = job
    f = Field.objects.get(key="photo_a")
    from apps.bookings.models import Booking

    with pytest.raises(CodedError) as e:
        services.submitted_answer(Booking.objects.get(pk=b["id"]), f)
    assert cast(dict, e.value.detail)["code"] == "NOT_SUBMITTED"


def test_a_file_id_that_is_not_a_uuid_finds_nothing(job):
    from apps.bookings.models import Booking

    assert services.live_asset(Booking.objects.get(pk=job[1]["id"]), "photo_a", "nope") is None


def test_ops_attach_only_their_own_live_file(job, settings):
    env, b = job
    submitted(env, b, settings)
    admins = ops_upload(env, b, settings, client=env.admin).json()["id"]
    r = env.ops.post(f"/api/v1/media/{admins}/attach", {}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "UNKNOWN_MEDIA"        # not theirs


def test_ops_cannot_add_to_a_full_field_by_attach(job, settings):
    env, b = job
    submitted(env, b, settings)                                                # photo_a takes 2
    first = ops_upload(env, b, settings).json()["id"]                         # both started while
    second = ops_upload(env, b, settings).json()["id"]                        # there was room
    assert env.ops.post(f"/api/v1/media/{first}/attach", {}, format="json").status_code == 204
    r = env.ops.post(f"/api/v1/media/{second}/attach", {}, format="json")
    assert r.status_code == 409 and r.json()["code"] == "TOO_MANY"


def test_a_late_ops_file_on_a_completed_booking_marks_the_report_out_of_date(job, settings):
    """Reports are made again only by Regenerate (plan-fixes F-219): a late file marks the PDF out of
    date and nothing renders by itself."""
    from apps.reports.models import Report

    env, b = job
    [a] = submitted(env, b, settings)
    a_asset = MediaAsset.objects.get(pk=a)
    a_asset.booking.stage = "completed"
    a_asset.booking.save(update_fields=["stage"])
    Report.objects.update_or_create(booking=a_asset.booking,
                                    defaults={"status": "ready", "stale": False})
    MediaAsset.objects.filter(pk=a).update(status="uploaded")
    with mock.patch("apps.reports.tasks.render_report.delay") as render:
        assert tasks.verify_asset(a) == "verified"
    render.assert_not_called()
    assert Report.objects.get(booking=a_asset.booking).stale is True


def test_zip_places_are_empty_when_the_booking_has_no_form(job):
    from apps.bookings.models import Booking

    with mock.patch("apps.bookings.submissions.current_versions",
                    side_effect=CodedError("NO_FORM", "x", 409)):
        assert zips._places(Booking.objects.get(pk=job[1]["id"])) == {}


def test_purge_also_drops_a_zip_that_was_never_built(job, settings):
    env, b = job
    [a] = submitted(env, b, settings)
    asset = MediaAsset.objects.get(pk=a)
    asset.booking.stage = "completed"
    asset.booking.save(update_fields=["stage"])
    MediaAsset.objects.filter(pk=a).update(created_at=asset.created_at.replace(year=2000))
    MediaZip.objects.create(booking=asset.booking, kind="photo", key="")     # still preparing
    with mock.patch("apps.core.app_settings.get", return_value={"photo_days": 1, "video_days": 0}):
        assert tasks.purge_expired() == 1
    assert not MediaZip.objects.filter(booking=asset.booking).exists()


def test_taking_back_a_file_also_clears_it_from_draft_answers(job, settings):
    env, b = job
    mine = upload(env.expert, b["id"], jpeg(color=(9, 9, 1)), settings).json()["id"]
    other = upload(env.expert, b["id"], jpeg(color=(9, 9, 2)), settings).json()["id"]
    draft = Inspection.objects.get(booking_id=b["id"], status="draft")
    draft.answers = {"inspection": {"photo_a": [mine, other], "sign": mine, "note": "x"}}
    draft.save()
    r = env.expert.delete(f"/api/v1/media/{mine}")
    assert r.status_code == 204
    draft.refresh_from_db()
    assert draft.answers["inspection"] == {"photo_a": [other], "note": "x"}
    assert draft.last_change["keys"] == ["photo_a"]
