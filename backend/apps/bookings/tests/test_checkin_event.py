"""checkin.completed (docs/plan-checkin-event.md): once per check-in, when every check-in file is
verified or 5 minutes after the check-in reached the server, whichever comes first."""
from datetime import timedelta
from unittest import mock

import pytest
from django.conf import settings as django_settings
from django.utils import timezone

from apps.bookings import checkin, tasks
from apps.bookings.models import Booking, Inspection
from apps.bookings.tests.test_submissions import _publish_with, assign, ienv, start  # noqa: F401
from apps.core import events
from apps.forms.models import Field
from apps.media.models import MediaAsset
from apps.media.tests.conftest import initiate_body, jpeg, put_parts, s3  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture
def cenv(ienv):
    """A published Check-in form (its selfie is required)."""
    _publish_with(ienv.admin, "start")
    return ienv


def register(env, b, data=None):
    """The phone registers the selfie before it sends the start: the file is still on the phone."""
    data = data or jpeg()
    r = env.expert.post("/api/v1/media/initiate", initiate_body(b["id"], data, field_key="selfie"),
                        format="json")
    assert r.status_code == 201, r.json()
    return r.json(), data


def upload(env, init, data, settings):
    """The bytes arrive and the file is checked (at once in tests)."""
    parts = put_parts(init, data, settings)
    r = env.expert.post(f"/api/v1/media/{init['id']}/complete", {"parts": parts}, format="json")
    assert r.status_code == 200, r.json()


def check_in(env, b, sid, **extra):
    r = start(env.expert, b, start_answers={"selfie": [sid]}, **extra)
    assert r.status_code == 200, r.json()
    return Inspection.objects.get(pk=r.json()["inspection"]["id"])


def fired(seen):
    return [p for n, p in seen if n == "checkin.completed"]


def test_it_waits_for_the_selfie_and_fires_when_it_is_verified(cenv, booking, settings, logged):
    assign(cenv, booking)
    init, data = register(cenv, booking)
    with events.capture() as seen:
        insp = check_in(cenv, booking, init["id"])
    assert fired(seen) == []                                    # the selfie is still on the phone
    assert insp.checkin_due_at is not None and insp.checkin_sent_at is None
    assert checkin.maybe_fire(insp.id) is False                 # another file's check: still waits
    [waiting] = logged("checkin.waiting")                       # logged once, on arrival
    assert (waiting["booking"], waiting["inspection"], waiting["files"]) == (
        booking["id"], str(insp.id), 1)
    with events.capture() as seen:
        upload(cenv, init, data, settings)
    [event] = fired(seen)
    assert event == {"booking": booking["id"], "booking_id": booking["booking_id"],
                     "inspection": str(insp.id), "missing": [], "number": 1}
    [done] = logged("checkin.fired")
    assert done["timed_out"] is False and done["missing"] == 0 and done["number"] == 1
    assert "selfie" not in str(done)                          # ids and counts only
    assert Inspection.objects.get(pk=insp.pk).checkin_sent_at is not None


def test_a_check_in_whose_files_are_already_verified_fires_at_once(cenv, booking, settings):
    assign(cenv, booking)
    init, data = register(cenv, booking)
    upload(cenv, init, data, settings)
    with events.capture() as seen:
        check_in(cenv, booking, init["id"])
    assert len(fired(seen)) == 1


def test_a_check_in_without_files_fires_at_once(cenv, booking, settings):
    assign(cenv, booking)
    init, _ = register(cenv, booking)
    insp = check_in(cenv, booking, init["id"])
    Inspection.objects.filter(pk=insp.pk).update(answers={"start": {}})   # nothing to wait for
    with events.capture() as seen:
        assert checkin.maybe_fire(insp.id) is True
    assert fired(seen)[0]["missing"] == []


def test_after_five_minutes_it_fires_and_names_the_missing_files(cenv, booking, settings, logged):
    assign(cenv, booking)
    init, _ = register(cenv, booking)
    insp = check_in(cenv, booking, init["id"])
    assert insp.checkin_due_at - timezone.now() > timedelta(minutes=4, seconds=50)
    with events.capture() as seen:
        tasks.checkin_due()                                     # not due yet
    assert fired(seen) == []
    Inspection.objects.filter(pk=insp.pk).update(checkin_due_at=timezone.now())
    with events.capture() as seen:
        tasks.checkin_due()
        tasks.checkin_due()                                     # the next minute: nothing again
    label = Field.objects.get(version=insp.start_version, key="selfie").label
    [event] = fired(seen)
    assert event["missing"] == [label]
    assert logged("checkin.fired")[-1]["timed_out"] is True


def test_two_callers_at_once_fire_it_only_once(cenv, booking, settings):
    assign(cenv, booking)
    init, _ = register(cenv, booking)
    insp = check_in(cenv, booking, init["id"])
    later = timezone.now() + checkin.WAIT
    with events.capture() as seen:
        assert checkin.maybe_fire(insp.id, later) is True
        assert checkin.maybe_fire(insp.id, later) is False
    assert len(fired(seen)) == 1


def test_inspections_from_before_this_change_never_fire(cenv, booking, settings):
    assign(cenv, booking)
    init, _ = register(cenv, booking)
    insp = check_in(cenv, booking, init["id"])
    Inspection.objects.filter(pk=insp.pk).update(checkin_due_at=None)
    with events.capture() as seen:
        assert checkin.maybe_fire(insp.id, timezone.now() + timedelta(days=1)) is False
        tasks.checkin_due()
    assert fired(seen) == []


def test_a_form_without_a_check_in_does_not_fire(ienv, booking):
    assign(ienv, booking)                                       # no Check-in form published
    with events.capture() as seen:
        assert start(ienv.expert, booking).status_code == 200
    assert Inspection.objects.get().checkin_due_at is None and fired(seen) == []


def test_a_deleted_booking_does_not_fire(cenv, booking, settings):
    assign(cenv, booking)
    init, _ = register(cenv, booking)
    insp = check_in(cenv, booking, init["id"])
    Booking.objects.filter(pk=booking["id"]).delete()
    assert checkin.maybe_fire(insp.id, timezone.now() + checkin.WAIT) is False


def test_a_second_check_in_fires_again_with_its_number(cenv, booking, settings):
    assign(cenv, booking)
    init, data = register(cenv, booking)
    upload(cenv, init, data, settings)
    first = check_in(cenv, booking, init["id"])
    assert cenv.ops.post(f"/api/v1/bookings/{booking['id']}/force-release").status_code == 200
    from rest_framework.test import APIClient

    other, client = cenv.make_user(), APIClient()
    client.force_authenticate(other)
    assign(cenv, booking, other)
    cenv2 = type("E", (), {"expert": client})
    init2, data2 = register(cenv2, booking, jpeg(color=(1, 2, 3)))
    upload(cenv2, init2, data2, settings)
    with events.capture() as seen:
        second = check_in(cenv2, booking, init2["id"])
    [event] = fired(seen)
    assert event["inspection"] == str(second.id) != str(first.id) and event["number"] == 2


def test_the_clock_flag_is_set_before_it_fires(cenv, booking, settings):
    """The view used to set it after start() returned: a check-in without waiting fired first."""
    assign(cenv, booking)
    init, data = register(cenv, booking)
    upload(cenv, init, data, settings)
    at_fire = []

    def look(name, payload):
        if name == "checkin.completed":
            at_fire.append(Inspection.objects.get(pk=payload["inspection"]).unverified_time)

    events.subscribe(look)
    try:
        check_in(cenv, booking, init["id"], unverified_time=True)
    finally:
        events._subscribers.remove(look)
    assert at_fire == [True]
    assert Booking.objects.get(pk=booking["id"]).unverified_time is True


def test_start_and_the_file_check_only_queue_the_event_work(cenv, booking, settings):
    """A live check-in never runs event code: a bug in it cannot fail Start or the file check."""
    assign(cenv, booking)
    init, data = register(cenv, booking)
    with mock.patch.object(tasks.checkin_check, "delay") as queued, \
            mock.patch.object(checkin, "maybe_fire", side_effect=RuntimeError("bug")):
        insp = check_in(cenv, booking, init["id"])
        queued.assert_called_once_with(str(insp.id), True)
        upload(cenv, init, data, settings)                      # verify_asset runs in full
        assert queued.call_args_list[-1] == mock.call(str(insp.id))
    assert MediaAsset.objects.get(pk=init["id"]).status == "verified"


def test_a_failing_check_raises_so_it_is_reported_and_the_beat_tries_again(cenv, booking, settings):
    assign(cenv, booking)
    init, _ = register(cenv, booking)
    insp = check_in(cenv, booking, init["id"])
    with mock.patch.object(checkin, "maybe_fire", side_effect=RuntimeError("bug")), \
            pytest.raises(RuntimeError):
        tasks.checkin_check(str(insp.id))
    assert Inspection.objects.get(pk=insp.pk).checkin_sent_at is None


def test_the_beat_takes_the_oldest_first_in_batches(cenv, booking, settings, monkeypatch):
    assign(cenv, booking)
    init, _ = register(cenv, booking)
    insp = check_in(cenv, booking, init["id"])
    old = timezone.now() - timedelta(minutes=10)
    Inspection.objects.filter(pk=insp.pk).update(checkin_due_at=old)
    other = Inspection.objects.create(booking_id=booking["id"], expert=insp.expert,
                                      form_version=insp.form_version, status="released",
                                      start_version=insp.start_version,
                                      checkin_due_at=old + timedelta(minutes=1))
    monkeypatch.setattr(checkin, "BATCH", 1)
    with events.capture() as seen:
        tasks.checkin_due()
    assert [e["inspection"] for e in fired(seen)] == [str(insp.id)]
    assert Inspection.objects.get(pk=other.pk).checkin_sent_at is None


def test_the_tasks_have_limits_a_queue_and_a_beat():
    assert tasks.checkin_check.soft_time_limit == 30 and tasks.checkin_check.time_limit == 60
    assert tasks.checkin_due.soft_time_limit == 30 and tasks.checkin_due.time_limit == 60
    assert django_settings.CELERY_TASK_ROUTES["apps.bookings.tasks.*"] == {"queue": "notify"}
    beat = django_settings.CELERY_BEAT_SCHEDULE["checkin-due"]
    assert beat == {"task": "apps.bookings.tasks.checkin_due", "schedule": 60.0}
