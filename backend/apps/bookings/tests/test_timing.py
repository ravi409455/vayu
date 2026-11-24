"""Started late / finished too quickly, the timing settings, and who may see them."""
from datetime import datetime, timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import AuditLog
from apps.bookings import timing
from apps.bookings.models import Booking

from .test_submissions import GOOD, assign, ienv, start, submit  # noqa: F401

pytestmark = pytest.mark.django_db
URL = "/api/v1/settings/timing"


def test_defaults_ops_reads_only_admin_changes_and_it_is_audited(env):
    r = env.ops.get(URL)
    assert r.status_code == 200
    assert r.json() == {"late_grace_minutes": 15, "min_minutes_default": 30,
                        "min_minutes_by_type": {"pdi": 30, "used_car": 45, "ev": 40}}
    new = {"late_grace_minutes": 10, "min_minutes_default": 20, "min_minutes_by_type": {"pdi": 25}}
    assert env.ops.put(URL, new, format="json").status_code == 403
    assert env.expert.get(URL).status_code == 403
    r = env.admin.put(URL, new, format="json")
    assert r.status_code == 200 and env.ops.get(URL).json() == new
    log = AuditLog.objects.get(action="settings.timing")
    assert '"late_grace_minutes": 15' in log.summary and '"late_grace_minutes": 10' in log.summary


def test_bad_values_are_refused(env):
    for bad in ({"late_grace_minutes": -1, "min_minutes_default": 30},
                {"late_grace_minutes": "15", "min_minutes_default": 30},
                {"late_grace_minutes": 15, "min_minutes_default": 30,
                 "min_minutes_by_type": {"pdi": 99999}}):
        assert env.admin.put(URL, bad, format="json").status_code == 400
    assert env.admin.get("/api/v1/settings/nope").status_code == 404


def _booking(env, **cols):
    b = Booking.objects.get(booking_id="SA37926")           # booked 2026-10-14 15:30, PDI
    for k, v in cols.items():
        setattr(b, k, v)
    b.save()
    return b


def test_stamps_from_the_booked_time_and_the_server_clock(booking):
    b = Booking.objects.get(pk=booking["id"])
    b.started_at = timezone.make_aware(datetime(2026, 10, 14, 16, 10))
    timing.stamp_late(b)
    timing.stamp_duration(b, b.started_at + timedelta(minutes=25))
    assert (b.late_minutes, b.duration_minutes) == (40, 25)
    b.started_at = None                                      # Start never reached the server
    timing.stamp_late(b)
    timing.stamp_duration(b, timezone.now())
    assert (b.late_minutes, b.duration_minutes) == (None, None)


def test_flags_follow_the_limits_per_type(env, booking):
    b = _booking(env, late_minutes=16, duration_minutes=29)
    cfg = timing.config()
    f = timing.flags(b, cfg)
    assert f["late"] and f["quick"] and f["min_minutes"] == 30
    cfg["min_minutes_by_type"]["pdi"] = 20                  # a new limit re-flags at once
    cfg["late_grace_minutes"] = 20
    f = timing.flags(b, cfg)
    assert not f["late"] and not f["quick"]
    b.inspection_type = "tour"                               # no own number: the default
    assert timing.flags(b, cfg)["min_minutes"] == 30


def test_list_filters_and_the_flag_are_for_admin_and_ops_only(env, booking):
    _booking(env, late_minutes=40, duration_minutes=50)
    q = "/api/v1/bookings?timing="
    assert [b["booking_id"] for b in env.ops.get(q + "late").json()["results"]] == ["SA37926"]
    assert env.ops.get(q + "quick").json()["count"] == 0
    assert env.admin.get(q + "late&reviewed=0").json()["count"] == 1
    assert env.ops.get(q + "any").status_code == 400          # two different things: pick one
    row = env.ops.get(f"/api/v1/bookings/{booking['id']}").json()["timing"]
    assert row["late"] and row["late_minutes"] == 40 and not row["quick"]
    assign(env, booking)
    assert env.expert.get(q + "late").status_code == 403
    assert "timing" not in env.expert.get(f"/api/v1/bookings/{booking['id']}").json()


def test_late_and_quick_are_reviewed_apart(env, booking):
    _booking(env, late_minutes=40, duration_minutes=5)       # both: late start AND too quick
    env.ops_user.name = "Asha Agarwal"                       # people see the name, not the login
    env.ops_user.save(update_fields=["name"])
    url = f"/api/v1/bookings/{booking['id']}/timing-review"
    r = env.ops.post(url, {"flag": "late"}, format="json")
    t = r.json()["timing"]
    assert r.status_code == 200 and t["late_reviewed_by"] == "Asha Agarwal"
    assert t["quick_reviewed_at"] is None                    # the quick finish is still open
    assert env.ops.get("/api/v1/bookings?timing=late&reviewed=0").json()["count"] == 0
    assert env.ops.get("/api/v1/bookings?timing=quick&reviewed=0").json()["count"] == 1
    assert env.ops.post(url, {"flag": "quick"}, format="json").status_code == 200
    assert env.ops.get("/api/v1/bookings?timing=quick&reviewed=1").json()["count"] == 1
    kinds = [a["kind"] for a in env.ops.get(f"/api/v1/bookings/{booking['id']}/activity").json()]
    assert "late_reviewed" in kinds and "quick_reviewed" in kinds
    assert env.ops.post(url, {"flag": "both"}, format="json").status_code == 400
    assert env.expert.post(url, {"flag": "late"}, format="json").status_code == 403
    assign(env, booking)                                     # the expert's own timeline: no trace
    kinds = [a["kind"] for a in env.expert.get(f"/api/v1/bookings/{booking['id']}/activity").json()]
    assert "late_reviewed" not in kinds and "quick_reviewed" not in kinds


def test_start_and_submit_stamp_the_minutes(ienv, booking):
    assign(ienv, booking)
    assert start(ienv.expert, booking).status_code == 200
    b = Booking.objects.get(pk=booking["id"])
    assert b.late_minutes is not None and b.late_minutes > 15   # booked weeks ago
    assert submit(ienv.expert, booking, GOOD).status_code == 200
    b.refresh_from_db()
    assert b.duration_minutes == 0                           # submitted at once: too quick
    assert ienv.ops.get("/api/v1/bookings?timing=quick").json()["count"] == 1


def test_force_release_clears_the_late_flag_and_its_review(ienv, booking):
    assign(ienv, booking)
    assert start(ienv.expert, booking).status_code == 200
    url = f"/api/v1/bookings/{booking['id']}"
    assert ienv.ops.post(url + "/timing-review", {"flag": "late"}, format="json").status_code == 200
    assert ienv.ops.post(url + "/force-release").status_code == 200
    t = ienv.ops.get(url).json()["timing"]
    assert t["late_minutes"] is None and t["late_reviewed_at"] is None   # the next start is judged afresh
