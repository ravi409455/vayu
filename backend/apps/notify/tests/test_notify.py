"""The bell and pushes: who hears about what, mute switches, push tokens, late starts."""
import hashlib
from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.accounts.models import Device, Role
from apps.bookings.models import Booking
from apps.bookings.tests.conftest import BASE, booking, create, env  # noqa: F401
from apps.bookings.tests.test_submissions import GOOD, assign, ienv, start, submit  # noqa: F401
from apps.notify import push as fcm
from apps.notify import tasks
from apps.notify.models import Notification

pytestmark = pytest.mark.django_db


def bell(client):
    r = client.get("/api/v1/notifications")
    assert r.status_code == 200
    return r.json()


def titles(client):
    return [n["title"] for n in bell(client)["results"]]


def test_expert_hears_assigned_moved_changed_and_cancelled(env, booking):
    assign(env, booking)
    b = booking["id"]
    r = env.ops.patch(f"/api/v1/bookings/{b}", {"answers": {"address": "Aundh"},
                      "row_version": Booking.objects.get(pk=b).row_version}, format="json")
    assert r.status_code == 200, r.json()
    got = bell(env.expert)
    assert got["unread"] == len(got["results"])
    t = [n["title"] for n in got["results"]]
    assert t[-1] == "New job: SA37926" and "SA37926 details changed" in t
    changed = next(n for n in got["results"] if n["kind"] == "changed")
    assert changed["body"] == "Address: 12 MG Road → Aundh" and changed["booking"] == b
    assert titles(env.ops) == []                       # Ops don't hear about their own edits


def test_reassigned_away_and_cancelled(env, booking):
    other = env.make_user(Role.EXPERT)
    assign(env, booking)
    assign(env, booking, other)
    assert "SA37926 moved to another expert" in titles(env.expert)
    Notification.objects.all().delete()
    with mock.patch("apps.bookings.services.active_item", return_value=True):
        assert env.ops.post(f"/api/v1/bookings/{booking['id']}/cancel", {"reason": "x"},
                            format="json").status_code == 200
    assert [n.title for n in Notification.objects.filter(user=other)] == ["SA37926 cancelled"]


def test_rescheduled_shows_old_and_new_time(env, booking):
    assign(env, booking)
    with mock.patch("apps.bookings.services.active_item", return_value=True):
        r = env.ops.post(f"/api/v1/bookings/{booking['id']}/reschedule",
                         {"date": "2026-10-16", "time": "10:00", "reason": "x"}, format="json")
    assert r.status_code == 200, r.json()
    n = Notification.objects.get(user=env.expert_user, kind="rescheduled")
    assert (n.title, n.body) == ("SA37926 moved", "2026-10-14 15:30 → 2026-10-16 10:00")


def test_ops_hear_progress_and_can_mute_all_but_problems(ienv, booking):
    muted = ienv.make_user(Role.OPS)
    muted.notify_prefs = {"started": False, "submitted": False}
    muted.save()
    assign(ienv, booking)
    assert start(ienv.expert, booking).status_code in (200, 201)
    assert submit(ienv.expert, booking).status_code == 200
    assert {"SA37926 started", "SA37926 submitted"} <= set(titles(ienv.ops))
    assert not Notification.objects.filter(user=muted).exists()
    from apps.core import events
    events.emit("alert.pdf_failed", booking=booking["id"], reason="x")
    assert [n.title for n in Notification.objects.filter(user=muted)] == [
        "Report failed for SA37926"]


def test_new_booking_only_when_it_came_from_the_api(env):
    from apps.bookings import services
    from apps.integrations.apikeys import service_user
    assert create(env.ops).status_code == 201
    assert titles(env.ops) == []
    services.create(service_user(), {**BASE, "booking_id": "ERP-1"})
    assert titles(env.ops) == ["New booking ERP-1"]


def test_read_some_or_all(env, booking):
    assign(env, booking)
    assign(env, booking, env.make_user(Role.EXPERT))
    rows = bell(env.expert)["results"]
    assert len(rows) == 2
    r = env.expert.post("/api/v1/notifications/read", {"ids": [rows[0]["id"]]}, format="json")
    assert r.json() == {"unread": 1}
    assert env.expert.post("/api/v1/notifications/read", {"ids": "x"},
                           format="json").status_code == 400
    assert env.expert.post("/api/v1/notifications/read", {"all": True},
                           format="json").json() == {"unread": 0}
    assert env.ops.post("/api/v1/notifications/read", {"all": True},
                        format="json").json() == {"unread": 0}   # nobody reads another's bell


def test_prefs_only_for_ops_and_only_known_switches(env):
    r = env.ops.patch("/api/v1/auth/me/profile", {"notify_prefs": {"new_bookings": False}},
                      format="json")
    assert r.status_code == 200 and r.json()["notify_prefs"] == {"new_bookings": False}
    for bad in ({"problem": False}, {"started": "no"}, ["started"]):
        assert env.ops.patch("/api/v1/auth/me/profile", {"notify_prefs": bad},
                             format="json").status_code == 400
    assert env.expert.patch("/api/v1/auth/me/profile", {"notify_prefs": {"started": False}},
                            format="json").status_code == 400
    assert env.ops.patch("/api/v1/auth/me/profile", {"theme": "dark"},
                         format="json").json()["notify_prefs"] == {"new_bookings": False}


def test_push_token_belongs_to_the_signed_in_phone(db, make_user, login):
    from rest_framework.test import APIClient
    u = make_user(Role.EXPERT)
    c = APIClient()
    tok = login(c, u.username, device_name="Pixel").json()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {tok['access']}")
    assert c.post("/api/v1/devices/push-token", {"token": "abc"}, format="json").status_code == 204
    assert Device.objects.get(pk=tok["device_id"]).push_token == "abc"
    assert c.post("/api/v1/devices/push-token", {"token": ""}, format="json").status_code == 400
    earlier = Device.objects.create(user=make_user(Role.OPS), push_token="abc",
                                    push_token_at=timezone.now() - timedelta(days=1))
    assert c.post("/api/v1/devices/push-token", {"token": "abc"}, format="json").status_code == 204
    earlier.refresh_from_db()
    assert earlier.push_token == "abc"            # someone else's row is never written
    assert c.post("/api/v1/auth/logout").status_code == 204
    assert Device.objects.get(pk=tok["device_id"]).push_token == ""   # signed out: token gone
    web = APIClient()
    web.force_authenticate(u)
    assert web.post("/api/v1/devices/push-token", {"token": "abc"},
                    format="json").status_code == 400


def test_push_sends_to_live_phones_and_forgets_dead_tokens(env, booking, settings):
    live = Device.objects.create(user=env.expert_user, push_token="live", push_token_at=timezone.now())
    Device.objects.create(user=env.expert_user, push_token="old", revoked_at=timezone.now())
    sent = []
    with mock.patch.object(fcm, "credential", return_value={"project_id": "p"}), \
            mock.patch.object(fcm, "send", side_effect=lambda t, d: sent.append((t, d)) or False):
        assign(env, booking)
    assert [t for t, _ in sent] == ["live"]
    assert sent[0][1]["kind"] == "assigned" and sent[0][1]["booking"] == booking["id"]
    assert sent[0][1]["user"] == str(env.expert_user.id)
    live.refresh_from_db()
    assert live.push_token == ""                      # dead token dropped
    assert tasks.push([]) == 0


def test_without_a_credential_nothing_is_sent(env, booking, settings):
    fcm.credential.cache_clear()
    settings.FCM_CREDENTIALS = ""
    assert fcm.credential() is None and fcm.send("t", {}) is True
    assert tasks.push([1]) == 0


def test_send_signs_in_and_reports_dead_tokens(settings, tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from django.core.cache import cache
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    f = tmp_path / "sa.json"
    f.write_text('{"client_email": "a@b", "token_uri": "https://t", "project_id": "p", '
                 f'"private_key": {key!r}}}'.replace("'", '"'))
    settings.FCM_CREDENTIALS = str(f)
    fcm.credential.cache_clear()
    cache.clear()
    ok = mock.Mock(status_code=200, text="{}")
    ok.json.return_value = {"access_token": "AT"}
    gone = mock.Mock(status_code=404, text='{"error": {"status": "UNREGISTERED"}}')
    bad = mock.Mock(status_code=500, text="oops")
    with mock.patch.object(fcm.requests, "post", side_effect=[ok, ok, gone, bad]) as post:
        assert fcm.send("t1", {"a": "1"}) is True
        assert fcm.send("t2", {}) is False            # token cached: no second sign-in
        assert fcm.send("t3", {}) is True             # other failures are logged, kept
    assert post.call_count == 4
    assert post.call_args_list[1].kwargs["headers"] == {"Authorization": "Bearer AT"}
    fcm.credential.cache_clear()


def test_late_start_once_per_job_using_the_settings_limit(env, booking):
    b = Booking.objects.get(pk=booking["id"])
    now = timezone.localtime()
    booked = now - timedelta(minutes=16)              # limit is 15 min by default
    b.answers = {**b.answers, "inspection_time": booked.strftime("%H:%M")}
    b.inspection_date = booked.date()
    b.save()
    assert tasks.late_starts() == 1
    assert tasks.late_starts() == 0                   # once per job
    n = Notification.objects.get(kind="late", user=env.ops_user)
    assert n.title == "SA37926 not started" and n.body.endswith(booked.strftime("%H:%M"))
    old = Notification.objects.create(user=env.ops_user, kind="x", title="old")
    Notification.objects.filter(pk=old.pk).update(created_at=now - timedelta(days=31))
    tasks.late_starts()
    assert not Notification.objects.filter(pk=old.pk).exists()


def test_not_late_inside_the_limit_or_when_unknown(env, booking):
    b = Booking.objects.get(pk=booking["id"])
    soon = timezone.localtime() - timedelta(minutes=5)
    b.answers = {**b.answers, "inspection_time": soon.strftime("%H:%M")}
    b.inspection_date = soon.date()
    b.save()
    assert tasks.late_starts() == 0
    b.answers = {**b.answers, "inspection_time": ""}
    b.save()
    assert tasks.late_starts() == 0


def test_app_latest_and_download(env, settings, tmp_path):
    from django.core.management import CommandError, call_command
    from rest_framework.test import APIClient
    settings.MIN_APP_VERSION = 3
    assert env.expert.get("/api/v1/app/latest").json() == {"version_code": None, "min_version": 3}
    assert APIClient().get("/api/v1/app/download").status_code == 401     # sign-in needed
    assert env.ops.get("/api/v1/app/download").status_code == 404
    apk = tmp_path / "app-release.apk"
    apk.write_bytes(b"PK fake apk")
    with mock.patch("apps.media.storage.upload_file") as up, \
            mock.patch("apps.media.storage.presign_get", return_value="https://r2/x"):
        call_command("publish_apk", str(apk), "--version-code", "5", "--version-name", "1.1.0",
                     "--notes", "Faster uploads\\nScan plates")
        assert up.call_args.args[1:] == ("app/vayu-5.apk", "application/vnd.android.package-archive")
        got = env.expert.get("/api/v1/app/latest").json()
        r = env.expert.get("/api/v1/app/download")
    assert got == {"version_code": 5, "version_name": "1.1.0", "size": 11, "min_version": 3,
                   "sha256": hashlib.sha256(b"PK fake apk").hexdigest(),
                   "notes": ["Faster uploads", "Scan plates"], "url": "https://r2/x"}
    assert r.status_code == 302 and r["Location"] == "https://r2/x"
    with pytest.raises(CommandError):
        call_command("publish_apk", str(apk), "--version-code", "5", "--version-name", "x")
    with pytest.raises(CommandError):
        call_command("publish_apk", str(tmp_path / "nope.txt"), "--version-code", "6",
                     "--version-name", "x")


def test_edge_cases_stay_quiet_or_summarise(env, booking):
    from apps.core import events
    from apps.notify import handlers
    events.emit("alert.conflict", booking="00000000-0000-0000-0000-000000000000")   # gone
    events.emit("booking.created")                                     # no booking in it
    events.emit("booking.assigned", booking=booking["id"])             # no expert in it
    events.emit("booking.updated", booking=booking["id"], changes={"address": ["a", "b"]})  # draft
    env.ops_user.is_active = False
    env.ops_user.save()
    events.emit("inspection.started", booking=booking["id"])          # no Ops left to tell
    assert not Notification.objects.exists()
    assert handlers._changed({"a_b": [1, 2], "c": [[1], [2]]}) == "A b, C"
    Device.objects.create(user=env.expert_user, push_token="live", push_token_at=timezone.now())
    with mock.patch.object(fcm, "credential", return_value={"project_id": "p"}), \
            mock.patch.object(fcm, "send", return_value=True):
        assign(env, booking)
        assert tasks.push(list(Notification.objects.values_list("id", flat=True))) == 1
    Booking.objects.filter(pk=booking["id"]).update(stage="cancelled")
    events.emit("booking.updated", booking=booking["id"], changes={"address": ["a", "b"]})
    assert Notification.objects.count() == 1          # a cancelled job's edits stay quiet
