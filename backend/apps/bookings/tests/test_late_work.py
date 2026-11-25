"""Work done offline that reaches the server late (plan batch 3: H-20 / F-104 / F-105, R-35 / F-131).

The phone pins the latest published form versions when the expert starts a lead. Its start may
reach the server after the Admin published a newer version: the inspection keeps the versions the
expert filled, if they really were the latest at the phone's start time (with a clock allowance).
"""
import uuid
from datetime import datetime, timedelta

import pytest

from apps.bookings.models import Booking, Inspection
from apps.bookings.tests.test_review_fixes import _checkin, _publish_system
from apps.bookings.tests.test_submissions import GOOD, assign, ienv, start, submit  # noqa: F401
from apps.core import events
from apps.forms.models import Form, FormVersion
from apps.media.tests.conftest import s3  # noqa: F401  (in-memory S3 for the selfie)
from apps.notify.models import AppRelease, Notification

from .conftest import custom_form, publish_draft

pytestmark = pytest.mark.django_db
STARTED = datetime.fromisoformat("2026-10-14T10:00:00+05:30")    # what start() sends


def _versions(form_type="custom", key="pdi"):
    q = FormVersion.objects.filter(status="published", form__type=form_type)
    if form_type == "custom":
        q = q.filter(form__key=key)
    return list(q.order_by("number"))


def _publish_new_inspection_version(env, at):
    """The Admin publishes a newer PDI version (with a new required field) at [at]."""
    form = custom_form(env.admin, "pdi")
    v = form["draft_version"]["id"]
    sec = env.admin.get(f"/api/v1/form-versions/{v}").json()["pages"][0]["sections"][0]["id"]
    r = env.admin.post(f"/api/v1/sections/{sec}/fields", {
        "key": "new_must", "label": "New", "type": "short_text", "required": True}, format="json")
    assert r.status_code == 201, r.json()
    publish_draft(env.admin, form["id"])
    FormVersion.objects.filter(pk=v).update(published_at=at)
    return FormVersion.objects.get(pk=v)


@pytest.fixture
def two_versions(ienv, booking):
    """v_old was published well before the phone's start; the booking is assigned."""
    old = _versions()[-1]
    FormVersion.objects.filter(form=old.form).update(published_at=STARTED - timedelta(days=10))
    Booking.objects.filter(pk=booking["id"]).update(created_at=STARTED - timedelta(days=1))
    assign(ienv, booking)
    return ienv, booking, FormVersion.objects.get(pk=old.pk)


def _start_on_app(env, booking, version: str):
    body = {"client_uuid": str(uuid.uuid4()), "client_started_at": STARTED.isoformat(),
            "inspection_type": "pdi"}
    return env.expert.post(f"/api/v1/bookings/{booking['id']}/start", body, format="json",
                           HTTP_X_APP_VERSION=version)


def _alerts(booking) -> list[str]:
    return [a["code"] for a in Booking.objects.get(pk=booking["id"]).alerts]


# ---------------------------------------------------------------- start keeps the phone's version

def test_a_version_published_after_the_phones_start_does_not_replace_the_one_it_filled(two_versions):
    env, booking, old = two_versions
    _publish_new_inspection_version(env, STARTED + timedelta(hours=2))
    r = start(env.expert, booking, form_version=old.id)
    assert r.status_code == 200, r.json()
    insp = Inspection.objects.get(booking_id=booking["id"])
    assert insp.form_version_id == old.id
    assert r.json()["form"]["id"] == old.id
    assert _alerts(booking) == ["LATE_WORK"]            # allowed, but Ops look at it
    # the answers are checked against the version the expert filled (no "new_must" there)
    assert submit(env.expert, booking).status_code == 200


def test_without_a_version_the_start_pins_the_latest_as_before(two_versions):
    env, booking, _ = two_versions
    new = _publish_new_inspection_version(env, STARTED + timedelta(hours=2))
    assert start(env.expert, booking).status_code == 200
    assert Inspection.objects.get(booking_id=booking["id"]).form_version_id == new.id
    assert _alerts(booking) == []


def test_the_latest_version_named_by_the_phone_raises_no_alert(two_versions):
    env, booking, old = two_versions
    assert start(env.expert, booking, form_version=old.id).status_code == 200
    assert _alerts(booking) == []


def test_a_start_time_before_the_booking_existed_is_not_believed(two_versions):
    env, booking, old = two_versions
    # replaced two days before the booking was made: the phone claims it started before that
    _publish_new_inspection_version(env, STARTED - timedelta(days=3))
    r = start(env.expert, booking, form_version=old.id,
              client_started_at=(STARTED - timedelta(days=5)).isoformat())
    assert r.status_code == 409 and r.json()["code"] == "FORM_VERSION_OLD"


def test_the_clock_allowance_covers_a_phone_a_few_minutes_off(two_versions):
    env, booking, old = two_versions
    _publish_new_inspection_version(env, STARTED - timedelta(minutes=5))
    assert start(env.expert, booking, form_version=old.id).status_code == 200
    assert Inspection.objects.get(booking_id=booking["id"]).form_version_id == old.id


def test_a_version_that_was_already_old_at_the_start_is_refused_and_ops_are_told(two_versions):
    env, booking, old = two_versions
    _publish_new_inspection_version(env, STARTED - timedelta(hours=3))
    with events.capture() as seen:
        r = start(env.expert, booking, form_version=old.id)
    assert r.status_code == 409 and r.json()["code"] == "FORM_VERSION_OLD"
    b = Booking.objects.get(pk=booking["id"])
    assert b.stage == "assigned" and not Inspection.objects.exists()
    assert _alerts(booking) == ["FORM_VERSION_REFUSED"]                  # kept despite the refusal
    assert ("alert.late_work", {"booking": booking["id"], "booking_id": b.booking_id,
                                "code": "FORM_VERSION_REFUSED"}) in seen
    assert Notification.objects.filter(user=env.ops_user, kind="problem").exists()
    again = start(env.expert, booking, form_version=old.id)              # the phone retries
    assert again.status_code == 409 and _alerts(booking) == ["FORM_VERSION_REFUSED"]  # told once


@pytest.mark.parametrize("bad", ["draft", "missing", "other_type", "text"])
def test_a_version_that_is_not_a_published_version_of_this_type_is_refused(two_versions, bad):
    env, booking, _ = two_versions
    other = custom_form(env.admin, "ev", "EV")
    publish_draft(env.admin, other["id"])
    Form.objects.filter(pk=other["id"]).update(inspection_type="ev")
    ids = {"draft": custom_form(env.admin, "pdi")["draft_version"]["id"], "missing": 999999,
           "other_type": _versions(key="ev")[-1].id, "text": "5"}
    r = start(env.expert, booking, form_version=ids[bad])
    assert r.status_code == 400 and r.json()["code"] == "INVALID_VERSION"
    assert Booking.objects.get(pk=booking["id"]).stage == "assigned"


def test_the_check_in_is_checked_against_the_start_form_the_phone_pinned(two_versions, settings):
    env, booking, old = two_versions
    _publish_system(env.admin, "start", "first_q")
    start_v1 = _versions("start")[-1]
    FormVersion.objects.filter(pk=start_v1.pk).update(published_at=STARTED - timedelta(days=1))
    # a newer check-in with a required question, published after the phone started
    form = Form.objects.get(type="start")
    draft = env.admin.post(f"/api/v1/forms/{form.id}/drafts").json()["id"]
    sec = env.admin.get(f"/api/v1/form-versions/{draft}").json()["pages"][0]["sections"][0]["id"]
    env.admin.post(f"/api/v1/sections/{sec}/fields", {"key": "second_q", "label": "q",
                   "type": "yes_no", "required": True}, format="json")
    publish_draft(env.admin, form.id)
    FormVersion.objects.filter(pk=draft).update(published_at=STARTED + timedelta(hours=1))
    r = start(env.expert, booking, form_version=old.id, start_version=start_v1.id,
              **_checkin(env, booking, settings))
    assert r.status_code == 200, r.json()
    assert Inspection.objects.get(booking_id=booking["id"]).start_version_id == start_v1.id


@pytest.mark.parametrize("bad", ["custom", "text"])
def test_a_start_version_from_another_form_is_refused(two_versions, bad):
    env, booking, old = two_versions
    _publish_system(env.admin, "start", "first_q")
    r = start(env.expert, booking, form_version=old.id,
              start_version=old.id if bad == "custom" else "x")
    assert r.status_code == 400 and r.json()["code"] == "INVALID_VERSION"


def test_an_old_end_form_is_refused_like_the_inspection_form(two_versions):
    env, booking, old = two_versions
    _publish_system(env.admin, "end", "first_end")
    end_v1 = _versions("end")[-1]
    FormVersion.objects.filter(pk=end_v1.pk).update(published_at=STARTED - timedelta(days=2))
    form = Form.objects.get(type="end")
    env.admin.post(f"/api/v1/forms/{form.id}/drafts")
    _publish_system(env.admin, "end", "second_end")
    FormVersion.objects.filter(pk=_versions("end")[-1].pk).update(
        published_at=STARTED - timedelta(days=1))
    r = start(env.expert, booking, form_version=old.id, end_version=end_v1.id)
    assert r.status_code == 409 and r.json()["code"] == "FORM_VERSION_OLD"


def test_a_start_or_end_version_is_ignored_when_the_form_does_not_use_it(two_versions):
    env, booking, old = two_versions
    FormVersion.objects.filter(pk=old.pk).update(use_start=False, use_end=False)
    _publish_system(env.admin, "end", "first_end")
    r = start(env.expert, booking, form_version=old.id, end_version=_versions("end")[-1].id)
    assert r.status_code == 200
    assert Inspection.objects.get(booking_id=booking["id"]).end_version_id is None


# ---------------------------------------------------------------- R-35 / F-131 late delivery

def test_a_start_on_a_form_switched_off_since_is_accepted_and_ops_are_told(two_versions):
    env, booking, old = two_versions
    Form.objects.filter(pk=old.form_id).update(is_active=False)
    refused = start(env.expert, booking)                     # no version named: nothing to fill
    assert refused.status_code == 409 and refused.json()["code"] == "NO_INSPECTION_FORM"
    with events.capture() as seen:
        r = start(env.expert, booking, form_version=old.id)
    assert r.status_code == 200, r.json()
    assert Inspection.objects.get(booking_id=booking["id"]).form_version_id == old.id
    (alert,) = Booking.objects.get(pk=booking["id"]).alerts
    assert alert["code"] == "LATE_WORK" and "switched off" in alert["detail"]
    assert "alert.late_work" in [n for n, _ in seen]


def test_a_submit_alone_on_a_form_switched_off_since_is_accepted_and_ops_are_told(two_versions):
    env, booking, old = two_versions
    Form.objects.filter(pk=old.form_id).update(is_active=False)
    r = submit(env.expert, booking, form_version=old.id)
    assert r.status_code == 200, r.json()
    assert Inspection.objects.get(booking_id=booking["id"]).form_version_id == old.id
    assert _alerts(booking) == ["LATE_WORK"]


def test_a_submit_alone_on_an_older_version_still_valid_since_the_booking_is_accepted(two_versions):
    env, booking, old = two_versions
    _publish_new_inspection_version(env, STARTED + timedelta(hours=2))   # after the booking
    r = submit(env.expert, booking, form_version=old.id)
    assert r.status_code == 200, r.json()
    assert _alerts(booking) == ["LATE_WORK"]


def test_a_submit_alone_on_a_version_replaced_before_the_booking_existed_is_refused(two_versions):
    env, booking, old = two_versions
    _publish_new_inspection_version(env, STARTED - timedelta(days=3))
    r = submit(env.expert, booking, form_version=old.id)
    assert r.status_code == 409 and r.json()["code"] == "FORM_VERSION_OLD"
    assert not Inspection.objects.exists() and _alerts(booking) == ["FORM_VERSION_REFUSED"]


def test_work_started_before_the_app_became_too_old_is_accepted(two_versions, settings):
    env, booking, _ = two_versions
    settings.MIN_APP_VERSION = 10
    AppRelease.objects.create(version_code=10, version_name="1.10", file_key="k", size=1,
                              sha256="0" * 64, created_at=STARTED + timedelta(hours=1))
    r = _start_on_app(env, booking, "9")
    assert r.status_code == 200, r.json()
    assert _alerts(booking) == ["LATE_WORK"]


@pytest.mark.parametrize("release_at", [STARTED - timedelta(hours=1), None])
def test_new_work_on_a_too_old_app_still_needs_the_update(two_versions, settings, release_at):
    env, booking, _ = two_versions
    settings.MIN_APP_VERSION = 10
    if release_at is not None:
        AppRelease.objects.create(version_code=11, version_name="1.11", file_key="k", size=1,
                                  sha256="0" * 64, created_at=release_at)
    assert _start_on_app(env, booking, "9").status_code == 426
    no_time = env.expert.post(f"/api/v1/bookings/{booking['id']}/start",
                              {"client_uuid": str(uuid.uuid4()),
                               "inspection_type": "pdi"}, format="json", HTTP_X_APP_VERSION="9")
    assert no_time.status_code == 426


def test_a_too_old_app_cannot_date_its_start_before_the_booking_existed(two_versions, settings):
    env, booking, _ = two_versions          # the booking was made a day before STARTED
    settings.MIN_APP_VERSION = 10
    AppRelease.objects.create(version_code=10, version_name="1.10", file_key="k", size=1,
                              sha256="0" * 64, created_at=STARTED - timedelta(days=2))
    early = (STARTED - timedelta(days=3)).isoformat()      # before the build, and the booking
    r = env.expert.post(f"/api/v1/bookings/{booking['id']}/start",
                        {"client_uuid": str(uuid.uuid4()), "client_started_at": early,
                         "inspection_type": "pdi"}, format="json", HTTP_X_APP_VERSION="9")
    assert r.status_code == 426


# ---------------------------------------------------------------- sync keeps the drafts' forms

def test_sync_sends_the_forms_the_phones_drafts_use_even_when_no_job_uses_them(two_versions):
    env, booking, old = two_versions
    new = _publish_new_inspection_version(env, STARTED)
    body = env.expert.get("/api/v1/sync/jobs", {"drafts": f"{old.id}"}).json()
    assert body["jobs"][0]["versions"]["inspection"] == new.id
    assert {str(old.id), str(new.id)} <= set(body["forms"])
    tree = body["forms"][str(old.id)]
    assert "rating_config" not in tree                                  # filtered as for any job
    again = env.expert.get("/api/v1/sync/jobs", {"drafts": f"{old.id}",
                                                 "have": f"{old.id},{new.id}"}).json()
    assert again["forms"] == {}                                         # the phone has them


def test_sync_never_sends_unpublished_or_unknown_versions_for_drafts(two_versions):
    env, booking, _ = two_versions
    draft = custom_form(env.admin, "pdi")["draft_version"]["id"]
    body = env.expert.get("/api/v1/sync/jobs", {"drafts": f"{draft},999999"}).json()
    assert str(draft) not in body["forms"] and "999999" not in body["forms"]
    assert env.expert.get("/api/v1/sync/jobs", {"drafts": "x"}).status_code == 400
