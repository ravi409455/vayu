"""Plan batch 2 (bookings side): the inspection that counts, conflicts, second submits, drafts.

C-01 / F-098: no completion while a conflict is open; the report keeps the inspection that
counted. H-05 / F-053: a second submit by the same expert is refused. H-08 / F-102: force-release
closes the expert's draft; one open draft per expert per booking.
"""
import uuid
from importlib import import_module
from unittest import mock

import pytest
from django.apps import apps as django_apps
from django.db import IntegrityError, connection, transaction
from rest_framework.test import APIClient

from apps.bookings.models import Booking, Inspection
from apps.bookings.tests.test_submissions import GOOD, assign, ienv, start, started, submit  # noqa: F401
from apps.media.tests.conftest import s3  # noqa: F401

pytestmark = pytest.mark.django_db


def _other(env, name="sana"):
    user = env.make_user("expert", username=name)
    client = APIClient()
    client.force_authenticate(user=user)
    return user, client


def _late_conflict(env, booking):
    """Expert A started; Ops force-release and give the job to B, who finishes it; then A's
    offline work arrives (odometer 99999)."""
    sana, sc = _other(env)
    env.ops.post(f"/api/v1/bookings/{booking['id']}/force-release")
    assign(env, booking, sana)
    assert start(sc, booking).status_code == 200
    assert submit(sc, booking).status_code == 200
    assert Booking.objects.get(pk=booking["id"]).stage == "completed"
    late = submit(env.expert, booking, answers={"inspection": {**GOOD["inspection"],
                                                               "odometer": 99999}})
    assert late.status_code == 200
    return sana


# ---------------------------------------------------------------- the counted inspection

def test_the_counted_inspection_is_the_newest_submitted_one(started):
    env, booking, _ = started
    b = Booking.objects.get(pk=booking["id"])
    assert b.counted_inspection() is None                       # only a draft
    submit(env.expert, booking)
    assert b.counted_inspection() == Inspection.objects.get(status="submitted")


def test_a_late_submit_on_a_completed_booking_never_replaces_what_counts(started):
    env, booking, _ = started
    sana = _late_conflict(env, booking)
    b = Booking.objects.get(pk=booking["id"])
    assert b.stage == "completed" and b.conflict == "TWO_EXPERTS"
    counted = b.counted_inspection()
    assert counted is not None and counted.expert_id == sana.id      # the customer's report
    assert counted.answers["inspection"]["odometer"] == 45


def test_a_conflict_that_comes_with_the_first_submission_counts_nothing(started):
    env, booking, _ = started
    env.ops.post(f"/api/v1/bookings/{booking['id']}/force-release")
    submit(env.expert, booking)                                  # the released draft arrives
    b = Booking.objects.get(pk=booking["id"])
    assert b.conflict == "RELEASED_DRAFT_ARRIVED" and b.stage == "submitted"
    assert b.counted_inspection() is None                        # no report until Ops choose


def test_ops_cannot_finish_a_booking_while_its_conflict_is_open(started):
    env, booking, _ = started
    env.ops.post(f"/api/v1/bookings/{booking['id']}/force-release")
    submit(env.expert, booking)
    r = env.ops.post(f"/api/v1/bookings/{booking['id']}/finish")
    assert r.status_code == 409 and r.json()["code"] == "CONFLICT_OPEN"


def test_resolving_a_completed_booking_makes_its_report_once_from_the_kept_one(started):
    env, booking, _ = started
    _late_conflict(env, booking)
    mine = Inspection.objects.get(booking_id=booking["id"], expert=env.expert_user,
                                  status="submitted")
    with mock.patch("apps.reports.tasks.render_report.delay") as render:
        r = env.ops.post(f"/api/v1/bookings/{booking['id']}/resolve-conflict",
                         {"inspection": str(mine.id)}, format="json")
    assert r.status_code == 200
    render.assert_called_once_with(booking["id"])
    assert Booking.objects.get(pk=booking["id"]).counted_inspection() == mine


def test_resolving_a_booking_still_waiting_completes_it_without_a_second_render(started):
    env, booking, _ = started
    env.ops.post(f"/api/v1/bookings/{booking['id']}/force-release")
    submit(env.expert, booking)
    keep = Inspection.objects.get(booking_id=booking["id"])
    with mock.patch("apps.reports.tasks.render_report.delay") as render:
        env.ops.post(f"/api/v1/bookings/{booking['id']}/resolve-conflict",
                     {"inspection": str(keep.id)}, format="json")
    assert Booking.objects.get(pk=booking["id"]).stage == "completed"
    assert render.call_count == 1                                # the completion's own render


# ---------------------------------------------------------------- H-05 second submit

@pytest.mark.parametrize("stage", ["completed", "submitted"])
def test_a_second_submit_by_the_same_expert_is_refused(started, stage):
    env, booking, s = started
    first = submit(env.expert, booking)
    assert first.status_code == 200
    Booking.objects.filter(pk=booking["id"]).update(stage=stage)
    again = submit(env.expert, booking, form_version=s["inspection"]["form_version"],
                   answers={"inspection": {**GOOD["inspection"], "chassis_no": "TAMPERED"}})
    assert again.status_code == 409 and again.json()["code"] == "ALREADY_SUBMITTED"
    assert Inspection.objects.filter(booking_id=booking["id"]).count() == 1


def test_the_same_request_id_still_returns_the_first_result(started):
    env, booking, _ = started
    sid = str(uuid.uuid4())
    body = {"client_submission_uuid": sid, "answers": GOOD}
    one = env.expert.post(f"/api/v1/bookings/{booking['id']}/submit", body, format="json")
    two = env.expert.post(f"/api/v1/bookings/{booking['id']}/submit", body, format="json")
    assert one.status_code == two.status_code == 200
    assert one.json()["inspection"]["id"] == two.json()["inspection"]["id"]


def test_an_expert_whose_inspection_ops_set_aside_cannot_submit_again(started):
    env, booking, s = started
    submit(env.expert, booking)
    Inspection.objects.filter(booking_id=booking["id"]).update(status="superseded")
    r = submit(env.expert, booking, form_version=s["inspection"]["form_version"])
    assert r.status_code == 409 and r.json()["code"] == "ALREADY_SUBMITTED"


# ---------------------------------------------------------------- H-08 drafts

def test_force_release_then_a_restart_fills_the_new_draft(started):
    env, booking, s = started
    assert env.ops.post(f"/api/v1/bookings/{booking['id']}/force-release").status_code == 200
    assert Inspection.objects.get(pk=s["inspection"]["id"]).status == "released"
    again = start(env.expert, booking)
    assert again.status_code == 200
    new = again.json()["inspection"]["id"]
    assert new != s["inspection"]["id"]
    assert submit(env.expert, booking).status_code == 200
    rows = dict(Inspection.objects.filter(booking_id=booking["id"]).values_list("id", "status"))
    assert {str(k): v for k, v in rows.items()} == {s["inspection"]["id"]: "released",
                                                     new: "submitted"}


def test_a_released_draft_no_longer_keeps_the_job_in_the_experts_lists(started):
    env, booking, _ = started
    env.ops.post(f"/api/v1/bookings/{booking['id']}/force-release")
    other, _ = _other(env, "cee")
    Booking.objects.filter(pk=booking["id"]).update(assigned_expert=other)   # no timeline row
    assert env.expert.get(f"/api/v1/bookings/{booking['id']}").status_code == 404


def test_sync_still_names_a_released_draft_as_mine(started):
    env, booking, s = started
    env.ops.post(f"/api/v1/bookings/{booking['id']}/force-release")
    (job,) = env.expert.get("/api/v1/sync/jobs").json()["jobs"]
    assert job["my_draft"] == s["inspection"]["id"]


def test_the_database_allows_one_open_draft_per_expert_per_booking(started):
    env, booking, _ = started
    mine = Inspection.objects.get(booking_id=booking["id"])
    with pytest.raises(IntegrityError), transaction.atomic():
        Inspection.objects.create(booking_id=booking["id"], expert=env.expert_user,
                                  form_version=mine.form_version, client_start_uuid=uuid.uuid4())


def test_the_migration_closes_the_extra_drafts_that_exist_today(started):
    env, booking, _ = started
    mine = Inspection.objects.get(booking_id=booking["id"])
    constraint = next(c for c in Inspection._meta.constraints
                      if c.name == "one_open_draft_per_expert")
    def ddl(fn):
        with connection.cursor() as c:
            c.execute("SET CONSTRAINTS ALL IMMEDIATE")      # no pending checks before DDL
        with connection.schema_editor() as editor:
            fn(editor)

    ddl(lambda e: e.remove_constraint(Inspection, constraint))   # as before the rule
    newer = Inspection.objects.create(booking_id=booking["id"], expert=env.expert_user,
                                      form_version=mine.form_version,
                                      client_start_uuid=uuid.uuid4())
    migration = import_module("apps.bookings.migrations.0009_close_extra_drafts")
    migration.close_extra_drafts(django_apps, None)
    assert Inspection.objects.get(pk=mine.pk).status == "released"
    assert Inspection.objects.get(pk=newer.pk).status == "draft"   # the newest stays open
    migration.reopen(django_apps, None)
    assert Inspection.objects.get(pk=mine.pk).status == "draft"
    Inspection.objects.filter(pk=newer.pk).delete()
    ddl(lambda e: e.add_constraint(Inspection, constraint))
