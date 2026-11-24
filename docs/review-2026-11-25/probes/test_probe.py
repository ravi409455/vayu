import uuid
from unittest import mock

import pytest

from apps.accounts.models import Role, User
from apps.bookings.models import Booking, Inspection
from apps.bookings.tests.conftest import env, booking, create  # noqa
from apps.bookings.tests.test_submissions import ienv, started, assign, start, submit, GOOD  # noqa
from apps.media.tests.conftest import s3  # noqa
from apps.forms.models import MasterListItem
from apps.notify.models import Notification

pytestmark = pytest.mark.django_db


def test_edit_fails_after_lead_owner_deactivated(env):
    owner = env.make_user(Role.OPS, username="leaver")
    b = create(env.ops, booking_id="P1", lead_owner=owner.id).json()
    User.objects.filter(pk=owner.pk).update(is_active=False)
    r = env.ops.patch(f"/api/v1/bookings/{b['id']}", {"answers": {"customer_name": "Asha K"},
                      "row_version": b["row_version"]}, format="json")
    print("LEAD_OWNER", r.status_code, r.json())


def test_edit_fails_after_city_archived(env):
    b = create(env.ops, booking_id="P2").json()
    MasterListItem.objects.filter(list__key="city", key="delhi").update(archived=True)
    r = env.ops.patch(f"/api/v1/bookings/{b['id']}", {"answers": {"customer_name": "Asha K"},
                      "row_version": b["row_version"]}, format="json")
    print("CITY", r.status_code, r.json())


def test_resubmit_new_uuid_same_expert(started):
    env, b, s = started
    assert submit(env.expert, b).status_code == 200
    v = s["inspection"]["form_version"]
    r = submit(env.expert, b, form_version=v)
    print("RESUBMIT", r.status_code, r.json().get("code"),
          Inspection.objects.filter(booking_id=b["id"], status="submitted").count(),
          repr(Booking.objects.get(pk=b["id"]).conflict))


def test_reassign_same_expert_twice(env, booking):
    assign(env, booking)
    assign(env, booking)
    print("NEWLEAD", list(Notification.objects.filter(user=env.expert_user).values_list("title", flat=True)))


def test_conflict_on_completed_rerenders_with_other_inspection(started):
    env, b, s = started
    from apps.reports import tasks
    sana = env.make_user(Role.EXPERT, username="sana")
    from rest_framework.test import APIClient
    sc = APIClient(); sc.force_authenticate(sana)
    # Ravi (expert) started; Ops force-release + reassign to Sana; Sana starts + submits -> completed
    env.ops.post(f"/api/v1/bookings/{b['id']}/force-release")
    assign(env, b, sana)
    assert start(sc, b).status_code == 200
    assert submit(sc, b).status_code == 200
    assert Booking.objects.get(pk=b["id"]).stage == "completed"
    from apps.reports.models import Report
    Report.objects.get_or_create(booking_id=b["id"])
    calls = []
    with mock.patch.object(tasks.render_report, "delay", side_effect=lambda x: calls.append(x)):
        r = submit(env.expert, b, answers={"inspection": {**GOOD["inspection"], "odometer": 99999}})
    got = Booking.objects.get(pk=b["id"])
    from apps.reports.context import latest_inspection
    li = latest_inspection(got)
    print("CONFLICT", r.status_code, got.stage, got.conflict, "render calls:", len(calls),
          "report uses expert:", li.expert.username, "odometer", li.answers["inspection"].get("odometer"))
