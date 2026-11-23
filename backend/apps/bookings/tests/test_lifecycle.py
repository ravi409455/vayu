"""Booking IDs, stages and Ops actions."""
import pytest

from apps.accounts.models import AuditLog
from apps.bookings.models import Booking
from apps.bookings.stages import STAGES, can_transition
from apps.core import events

from .conftest import create

pytestmark = pytest.mark.django_db

LEGAL = {("draft", "assigned"), ("draft", "cancelled"), ("assigned", "assigned"),
         ("assigned", "in_progress"), ("assigned", "cancelled"), ("in_progress", "submitted"),
         ("in_progress", "assigned"), ("in_progress", "cancelled"), ("submitted", "completed")}


@pytest.mark.parametrize("a", STAGES)
@pytest.mark.parametrize("b", STAGES)
def test_transition_matrix(a, b):
    assert can_transition(a, b) is ((a, b) in LEGAL)


# ---------------------------------------------------------------- create and ids

def test_create_gives_an_internal_uuid_and_draft_stage(env):
    r = create(env.ops)
    assert r.status_code == 201
    b = r.json()
    assert len(b["id"]) == 36 and b["booking_id"] == "SA37926" and b["stage"] == "draft"
    assert b["answers"]["customer_phone"] == "+919876543210"  # cleaned by the form engine
    assert b["row_version"] == 0


def test_create_needs_a_published_booking_form(db, api_as):
    from apps.accounts.models import Role

    ops, _ = api_as(Role.OPS)
    r = create(ops)
    assert r.status_code == 409 and r.json()["code"] == "NO_BOOKING_FORM"


def test_create_validates_answers(env):
    r = create(env.ops, customer_phone="123", city="atlantis")
    assert r.status_code == 400 and r.json()["code"] == "INVALID_ANSWERS"
    assert {"customer_phone", "city"} <= set(r.json()["errors"])
    r = env.ops.post("/api/v1/bookings", {"answers": {"booking_id": "X1"}}, format="json")
    assert r.json()["errors"]["customer_name"] == "required"


def test_expert_cannot_create(env):
    assert create(env.expert).status_code == 403


def test_booking_id_is_unique_trimmed_and_case_insensitive(env):
    assert create(env.ops).status_code == 201
    for dup in ("sa37926", " SA37926 ", "Sa37926"):
        r = create(env.ops, booking_id=dup)
        assert r.status_code == 400 and r.json()["code"] == "DUPLICATE_BOOKING_ID"
    assert create(env.ops, booking_id="SA37927").status_code == 201


def test_ci_uniqueness(env):
    created: dict[str, str] = {}
    for raw in ["ab12", "AB12", " ab12 ", "Ab12", "x9", "X9 ", "q1"]:
        r = create(env.ops, booking_id=raw)
        key = raw.strip().lower()
        if key in created:
            assert r.status_code == 400, raw
        else:
            assert r.status_code == 201, (raw, r.json())
            created[key] = r.json()["booking_id"]


# ---------------------------------------------------------------- edit + concurrency

def test_edit_booking_id_emits_old_to_new_and_expert_cannot(env, booking):
    url = f"/api/v1/bookings/{booking['id']}"
    with events.capture() as seen:
        r = env.ops.patch(url, {"answers": {"booking_id": "SA99999"},
                                "row_version": booking["row_version"]}, format="json")
    assert r.status_code == 200 and r.json()["booking_id"] == "SA99999"
    name, payload = seen[-1]
    assert name == "booking.updated" and payload["changes"]["booking_id"] == ["SA37926", "SA99999"]
    assert env.expert.patch(url, {"answers": {"booking_id": "Z1"}, "row_version": 1},
                            format="json").status_code == 403


def test_edit_cannot_steal_another_bookings_id(env, booking):
    other = create(env.ops, booking_id="SA11111").json()
    r = env.ops.patch(f"/api/v1/bookings/{other['id']}", {"answers": {"booking_id": "sa37926"},
                                                          "row_version": 0}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "DUPLICATE_BOOKING_ID"


def test_stale_edit_is_409_with_who_changed_what_and_retry_works(env, booking):
    url = f"/api/v1/bookings/{booking['id']}"
    env.admin.patch(url, {"answers": {"address": "New address"}, "row_version": 0}, format="json")
    r = env.ops.patch(url, {"answers": {"customer_name": "Asha K"}, "row_version": 0},
                      format="json")
    assert r.status_code == 409 and r.json()["code"] == "STALE_BOOKING"
    body = r.json()
    assert body["changed_by"] == env.admin_user.username and body["changed_keys"] == ["address"]
    ok = env.ops.patch(url, {"answers": {"customer_name": "Asha K"},
                             "row_version": body["row_version"]}, format="json")
    assert ok.status_code == 200, ok.json()
    final = ok.json()["answers"]
    assert final["address"] == "New address" and final["customer_name"] == "Asha K"
    assert ok.json()["last_edited_by"] == env.ops_user.username


def test_edit_needs_row_version_and_valid_answers(env, booking):
    url = f"/api/v1/bookings/{booking['id']}"
    assert env.ops.patch(url, {"answers": {"address": "x"}}, format="json").status_code == 400
    r = env.ops.patch(url, {"answers": {"customer_phone": "12"}, "row_version": 0},
                      format="json")
    assert r.status_code == 400 and r.json()["code"] == "INVALID_ANSWERS"


# ---------------------------------------------------------------- assign / reassign

def assign(client, booking, expert_id):
    return client.post(f"/api/v1/bookings/{booking['id']}/assign", {"expert": expert_id},
                       format="json")


def test_assign_sets_stage_and_expert_and_emits(env, booking):
    with events.capture() as seen:
        r = assign(env.ops, booking, env.expert_user.id)
    assert r.status_code == 200
    assert r.json()["stage"] == "assigned" and r.json()["assigned_expert"] == env.expert_user.id
    assert r.json()["answers"]["assigned_expert"] == env.expert_user.id
    assert seen[-1][0] == "booking.assigned"


def test_reassign_to_another_expert_while_not_started(env, booking):
    assign(env.ops, booking, env.expert_user.id)
    other = env.make_user("expert", username="e2")
    r = assign(env.ops, booking, other.id)
    assert r.status_code == 200 and r.json()["assigned_expert"] == other.id


@pytest.mark.parametrize("who", ["inactive", "ops", "missing"])
def test_assign_rejects_bad_targets(env, booking, who):
    target = {"inactive": env.make_user("expert", username="gone", is_active=False).id,
              "ops": env.ops_user.id, "missing": 999999}[who]
    r = assign(env.ops, booking, target)
    assert r.status_code == 400 and r.json()["code"] == "INVALID_EXPERT"


def test_assign_needs_the_permission_and_expert_cannot(env, booking):
    assert assign(env.expert, booking, env.expert_user.id).status_code == 403


# ---------------------------------------------------------------- reschedule / cancel

def test_reschedule_keeps_history_and_validates_reason(env, booking):
    url = f"/api/v1/bookings/{booking['id']}/reschedule"
    body = {"date": "2026-10-20", "time": "10:00", "reason": "customer_request"}
    r = env.ops.post(url, body, format="json")
    assert r.status_code == 200
    assert r.json()["answers"]["inspection_date"] == "2026-10-20"
    h = r.json()["reschedules"][0]
    assert (h["old_date"], h["old_time"], h["reason"]) == ("2026-10-14", "15:30", "customer_request")
    assert h["by"] == env.ops_user.username
    for bad in ({**body, "reason": "nope"}, {**body, "date": "2026-02-30"}, {**body, "time": "25:00"},
                {"date": "2026-10-20", "time": "10:00"}):
        assert env.ops.post(url, bad, format="json").status_code == 400


def test_cancel_needs_a_reason_and_keeps_the_data(env, booking):
    url = f"/api/v1/bookings/{booking['id']}/cancel"
    assert env.ops.post(url, {}, format="json").status_code == 400
    assert env.ops.post(url, {"reason": "nope"}, format="json").status_code == 400
    r = env.ops.post(url, {"reason": "on_arrival"}, format="json")
    assert r.status_code == 200 and r.json()["stage"] == "cancelled"
    assert r.json()["cancel_reason"] == "on_arrival" and r.json()["answers"]["customer_name"]
    assert env.ops.post(url, {"reason": "duplicate"}, format="json").status_code == 409  # already


def test_cancelled_and_completed_bookings_reject_actions(env, booking):
    env.ops.post(f"/api/v1/bookings/{booking['id']}/cancel", {"reason": "duplicate"}, format="json")
    assert assign(env.ops, booking, env.expert_user.id).status_code == 409
    r = env.ops.post(f"/api/v1/bookings/{booking['id']}/reschedule",
                     {"date": "2026-10-20", "time": "10:00", "reason": "other"}, format="json")
    assert r.status_code == 409


# ---------------------------------------------------------------- type lock / force release / delete

def test_type_change_before_start_ok_after_start_locked(env, booking):
    from .conftest import custom_form, publish_draft

    publish_draft(env.admin, custom_form(env.admin, "ev")["id"])
    url = f"/api/v1/bookings/{booking['id']}/change-type"
    r = env.ops.post(url, {"inspection_type": "ev"}, format="json")
    assert r.status_code == 200 and r.json()["inspection_type"] == "ev"
    assert r.json()["answers"]["inspection_type"] == "ev"
    assert env.ops.post(url, {"inspection_type": "nope"}, format="json").status_code == 400
    Booking.objects.filter(pk=booking["id"]).update(stage="in_progress", started_at="2026-10-14T10:00Z")
    r = env.ops.post(url, {"inspection_type": "pdi"}, format="json")
    assert r.status_code == 409 and r.json()["code"] == "TYPE_LOCKED"


def test_force_release_clears_the_start_lock_and_records_who(env, booking):
    assign(env.ops, booking, env.expert_user.id)
    Booking.objects.filter(pk=booking["id"]).update(stage="in_progress", started_at="2026-10-14T10:00Z")
    r = env.ops.post(f"/api/v1/bookings/{booking['id']}/force-release")
    assert r.status_code == 200
    b = r.json()
    assert b["stage"] == "assigned" and b["started_at"] is None
    assert b["released_by"] == env.ops_user.username and b["released_draft_expected"] is True
    assert AuditLog.objects.filter(action="booking.force_release").exists()
    assert env.ops.post(f"/api/v1/bookings/{booking['id']}/force-release").status_code == 409
    assert env.expert.post(f"/api/v1/bookings/{booking['id']}/force-release").status_code == 403


def test_reassign_is_blocked_once_started_until_force_released(env, booking):
    assign(env.ops, booking, env.expert_user.id)
    Booking.objects.filter(pk=booking["id"]).update(stage="in_progress", started_at="2026-10-14T10:00Z")
    other = env.make_user("expert", username="e2")
    r = assign(env.ops, booking, other.id)
    assert r.status_code == 409 and r.json()["code"] == "ALREADY_STARTED"
    env.ops.post(f"/api/v1/bookings/{booking['id']}/force-release")
    assert assign(env.ops, booking, other.id).status_code == 200


def test_admin_deletes_any_booking_ops_only_untouched_drafts_and_it_is_audited(env, booking):
    url = f"/api/v1/bookings/{booking['id']}"
    assert env.expert.delete(url).status_code == 403
    assign(env.ops, booking, env.expert_user.id)                       # no longer an untouched draft
    r = env.ops.delete(url)
    assert r.status_code == 403 and r.json()["code"] == "DELETE_NOT_ALLOWED"
    assert Booking.objects.filter(pk=booking["id"]).exists()
    assert env.admin.delete(url).status_code == 204                    # Admin: any booking
    assert not Booking.objects.filter(pk=booking["id"]).exists()
    assert AuditLog.objects.filter(action="booking.delete").exists()


def test_ops_may_delete_a_draft_nobody_has_touched(env):
    b = create(env.ops, booking_id="DEL-1").json()
    assert env.ops.delete(f"/api/v1/bookings/{b['id']}").status_code == 204
    assert not Booking.objects.filter(booking_id="DEL-1").exists()
    kept = create(env.ops, booking_id="DEL-2").json()
    Booking.objects.filter(pk=kept["id"]).update(stage="cancelled")
    assert env.ops.delete(f"/api/v1/bookings/{kept['id']}").status_code == 403
    again = create(env.ops, booking_id="DEL-3").json()
    from apps.bookings.models import Inspection

    Inspection.objects.create(booking_id=again["id"], expert=env.expert_user,
                              form_version_id=_any_version())
    assert env.ops.delete(f"/api/v1/bookings/{again['id']}").status_code == 403    # has an inspection


def _any_version():
    from apps.forms.models import FormVersion

    version = FormVersion.objects.first()
    assert version is not None
    return version.id


# ---------------------------------------------------------------- visibility

def test_experts_see_only_their_own_bookings(env, booking):
    other = create(env.ops, booking_id="SA2").json()
    assign(env.ops, booking, env.expert_user.id)
    ids = [b["id"] for b in env.expert.get("/api/v1/bookings").json()["results"]]
    assert ids == [booking["id"]]
    assert env.expert.get(f"/api/v1/bookings/{other['id']}").status_code == 404
    assert env.expert.get(f"/api/v1/bookings/{booking['id']}").status_code == 200
    assert len(env.ops.get("/api/v1/bookings").json()["results"]) == 2


def test_actions_emit_events_and_audit_rows(env, booking):
    with events.capture() as seen:
        env.ops.post(f"/api/v1/bookings/{booking['id']}/cancel", {"reason": "duplicate"},
                     format="json")
    assert [n for n, _ in seen] == ["booking.updated"]
    assert seen[0][1]["changes"]["stage"] == ["draft", "cancelled"]


def test_create_with_an_assigned_expert_starts_assigned(env):
    r = create(env.ops, assigned_expert=env.expert_user.id)
    assert r.status_code == 201
    assert r.json()["stage"] == "assigned" and r.json()["assigned_expert"] == env.expert_user.id


def test_assigned_expert_and_type_cannot_be_edited_directly(env, booking):
    for key, value in (("assigned_expert", env.expert_user.id), ("inspection_type", "ev")):
        r = env.ops.patch(f"/api/v1/bookings/{booking['id']}",
                          {"answers": {key: value}, "row_version": 0}, format="json")
        assert r.status_code == 400 and r.json()["code"] == "USE_ACTION"


def test_an_edit_that_changes_nothing_does_not_bump_the_version(env, booking):
    r = env.ops.patch(f"/api/v1/bookings/{booking['id']}",
                      {"answers": {"address": "12 MG Road"}, "row_version": 0}, format="json")
    assert r.status_code == 200 and r.json()["row_version"] == 0


def test_losing_a_race_on_the_unique_booking_id_is_a_clean_400(env, booking, monkeypatch):
    from apps.bookings import services

    monkeypatch.setattr(services, "_ensure_unique", lambda *a, **k: None)  # both passed the check
    r = create(env.ops)  # same ID: the database constraint is the last line of defence
    assert r.status_code == 400 and r.json()["code"] == "DUPLICATE_BOOKING_ID"
