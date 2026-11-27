"""Get a test server ready for the load tests (docs/plan-load-test.md). Never on production.

    python manage.py loadtest_prepare --password '<testers>' --receiver https://… --out /tmp/lt.json
        [--experts 50] [--ops 5] [--history-days 90] [--per-day 200] [--inspected-per-day 100]
        [--today 9]

It makes, once (running it again only adds what is missing):
- one login per simulated person: lt-expert-001… and lt-ops-01…;
- an API key for the external system (booking and PDI forms, every action);
- 20 webhook integrations pointing at the receiver: 10 on booking.created, 10 on PDI
  inspection.submitted, so a day of 200 bookings and 100 inspections sends exactly 15 per booking;
- the history: --history-days of finished bookings (copies of one real finished PDI, with their
  file records, report and webhook log), so the database is as full as after months of use;
- --today bookings for today, assigned round robin: the inspections the test's phones do;
- answer templates (start, PDI, end) from the real published forms, with the photo and video
  fields marked, so the phones submit what the app would.
Everything the load script needs (logins, key, booking ids, templates) goes to --out (0600)."""
import copy
import json
import os
import random
import uuid
from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.bookings import services
from apps.bookings.models import Booking, Inspection
from apps.forms.models import Form
from apps.integrations.models import ApiKey, Delivery, Integration
from apps.media.models import MediaAsset
from apps.platform.setup import testdata
from apps.reports.models import Report, new_token

PREFIX = "LT-"
PHOTOS_PER_INSPECTION = 100
BIG_PHOTOS = 150               # 2 of every 9 inspections: the old requirement's worst case
VIDEOS_REAL_FORM = 5           # the most today's forms allow: local runs (owner, 2026-11-27)
VIDEOS_TEST_FORM = 15          # the owner's number: cloud runs, on the test-only form


def _fresh(obj):
    """A copy that may be saved: a new id and new values for every unique id field."""
    from django.db import models

    c = copy.copy(obj)
    for f in c._meta.fields:
        if isinstance(f, models.UUIDField) and (f.primary_key or f.unique):
            setattr(c, f.attname, uuid.uuid4())
    return c


class _Marker:
    """Stands in for the phone's file uploads while answers are made: records which fields ask
    for a file, without storing anything."""

    def __init__(self):
        self.fields: dict[str, str] = {}

    def add(self, booking, who, field_key, caption, kind="photo"):
        self.fields[field_key] = kind
        return f"@{kind}"


def template(form_key: str, ns: str, others: dict, defects: float, seed: int) -> tuple[dict, dict]:
    """Answers for a form as the app sends them, and {field: kind} of the file fields asked."""
    marker = _Marker()
    rng = random.Random(seed)  # noqa: S311 - test data, not security
    dummy: Any = object()                  # fill() only checks a booking and a person are given
    answers = testdata.fill(testdata.live(form_key), ns, dummy, dummy, rng, marker,  # type: ignore[arg-type]
                            defects=defects, others=others)
    return answers, marker.fields


def file_plan(version, asked: dict, photos: int, videos: int) -> dict[str, int]:
    """How many files each asked field gets: `photos` and `videos` spread over the fields, never
    above a field's own limit."""
    from apps.forms.models import Field

    limits = {f.key: (f.config or {}).get("max_count", 1)
              for f in Field.objects.filter(version=version, key__in=asked)}
    plan = {k: 1 for k in asked}
    for kind, want in (("photo", photos), ("video", videos)):
        keys = [k for k, v in asked.items() if v == kind]
        have = len(keys)
        while have < want:
            grown = False
            for k in keys:
                if have < want and plan[k] < limits.get(k, 1):
                    plan[k] += 1
                    have += 1
                    grown = True
            if not grown:
                break
    return plan


class Command(BaseCommand):
    help = "Prepare a test server for the load tests (never production)."

    def add_arguments(self, p):
        p.add_argument("--password", required=True)
        p.add_argument("--receiver", required=True, help="the webhook receiver's base URL")
        p.add_argument("--out", required=True)
        p.add_argument("--experts", type=int, default=50)
        p.add_argument("--ops", type=int, default=5)
        p.add_argument("--history-days", type=int, default=90)
        p.add_argument("--per-day", type=int, default=200)
        p.add_argument("--inspected-per-day", type=int, default=100)
        p.add_argument("--today", type=int, default=9)
        p.add_argument("--unassigned", action="store_true",
                       help="leave today's bookings unassigned: the load script's Ops give each to "
                            "a free phone (the cloud runs, where the number of phones grows)")
        p.add_argument("--test-form", action="store_true",
                       help="use a test-only copy of PDI with extra photo/video fields (cloud "
                            "runs: 15 videos); off = the real PDI form, 5 videos (local runs)")

    def handle(self, *a, **o):
        from apps.platform.loadtest import Refused, check_test_server

        try:
            check_test_server()
        except Refused as e:
            raise CommandError(str(e)) from e
        if len(o["password"]) < 10:
            raise CommandError("Give the testers' password with --password (10+ characters).")
        self.form = "pdi"
        self.videos = VIDEOS_REAL_FORM
        if o["test_form"]:
            from apps.platform.loadtest import TEST_FORM, make_test_form

            admin = User.objects.filter(role=Role.ADMIN, is_active=True).first()
            if admin is None:
                raise CommandError("Run setup_platform first (it makes the Admin).")
            make_test_form(admin)
            self.form, self.videos = TEST_FORM, VIDEOS_TEST_FORM
        experts = self.users(Role.EXPERT, "lt-expert-", 3, o["experts"], o["password"])
        ops = self.users(Role.OPS, "lt-ops-", 2, o["ops"], o["password"])
        key = self.api_key()
        self.integrations(o["receiver"])
        found = self.found_or_template(ops[0], experts[0])
        self.history(found, experts, o["history_days"], o["per_day"], o["inspected_per_day"])
        today = self.today_bookings(ops[0], experts, o["today"], o["unassigned"])
        start, start_files = template("start", "start", {}, 0, 1)
        others = {"booking": found.answers, "start": start}
        insp, insp_files = self.pdi_template(others)
        end, end_files = template("end", "end", {}, 0, 3)
        version = testdata.live(self.form)
        out = {
            "password": o["password"],
            "experts": [u.username for u in experts], "expert_ids": [u.id for u in experts],
            "ops": [u.username for u in ops],
            "api_key": key,
            "inspection_type": self.form,
            # a valid booking (real list values) for the external system's new bookings
            "booking_answers": {k: v for k, v in found.answers.items() if k != "booking_id"},
            "today": today,
            # finished bookings the external system reads (an inspection exists for these)
            "done_refs": list(Booking.objects.filter(stage="completed",
                                                     booking_id__startswith=f"{PREFIX}H")
                              .order_by("-created_at").values_list("booking_id", flat=True)[:500]),
            "templates": {
                "start": {"answers": start, "files": file_plan(testdata.live("start"),
                                                                start_files, 1, 0)},
                "inspection": {"answers": insp, "files": file_plan(
                    version, insp_files, PHOTOS_PER_INSPECTION, self.videos)},
                "inspection_big": {"answers": insp, "files": file_plan(
                    version, insp_files, BIG_PHOTOS, self.videos)},
                "end": {"answers": end, "files": file_plan(testdata.live("end"), end_files, 0, 0)},
            },
        }
        fd = os.open(o["out"], os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(out, f)
        plan = out["templates"]["inspection"]["files"]
        self.stdout.write(f"Ready ({self.form} form): {len(experts)} experts, {len(ops)} Ops, "
                          f"{len(today)} bookings for today; an inspection sends "
                          f"{sum(n for k, n in plan.items() if insp_files[k] == 'photo')} photos "
                          f"and {sum(n for k, n in plan.items() if insp_files[k] == 'video')} "
                          f"videos. Details in {o['out']}.")

    # ------------------------------------------------------------------ people and keys

    def users(self, role, prefix, width, n, password):
        out = []
        for i in range(1, n + 1):
            name = f"{prefix}{i:0{width}d}"
            u = User.objects.filter(username=name).first()
            if u is None:
                u = User.objects.create_user(username=name, password=password, role=role,
                                             name=name, phone=f"97{i:08d}",
                                             must_change_password=False)
            elif not u.check_password(password):    # every run has its own password
                u.set_password(password)              # (a new password also ends any lock)
                u.save(update_fields=["password"])
            out.append(u)
        return out

    def api_key(self) -> str:
        from apps.integrations import apikeys

        ApiKey.objects.filter(name="load test", revoked_at=None).update(revoked_at=timezone.now())
        key, prefix, hashed = apikeys.generate()
        ApiKey.objects.create(name="load test", prefix=prefix, key_hash=hashed,
                              # the inspection form in use (pdi, or the test form): reading an
                              # inspection through the API needs it in the key's scope
                              scope={"forms": {"booking": ["*"], self.form: ["*"]}},
                              allowed_actions=["assign", "cancel", "reschedule", "change_type"])
        return key

    def integrations(self, receiver: str) -> None:
        """Made again every run, on the form in use: always exactly 10 + 10 to this receiver."""
        Integration.objects.filter(name__startswith="load test").delete()
        booking, pdi = Form.objects.get(key="booking"), Form.objects.get(key=self.form)
        for n in range(10):
            for form, event in ((booking, "booking.created"), (pdi, "inspection.submitted")):
                Integration.objects.create(form=form, name=f"load test {event} {n}", event=event,
                                           url=f"{receiver.rstrip('/')}/hook", include_data=False)

    # ------------------------------------------------------------------ history

    def found_or_template(self, ops, expert) -> Booking:
        """One real finished PDI (made the way the app makes one): the original the history
        copies."""
        b = Booking.objects.filter(booking_id=f"{PREFIX}TEMPLATE").first()
        if b is not None:
            return b
        bl = testdata.Builder({"ops": ops}, seed=11)
        b = bl.booking(timezone.localdate() - timedelta(days=1), "10:00", self.form,
                       booking_id=f"{PREFIX}TEMPLATE")
        bl.done(b, expert, timezone.now() - timedelta(days=1), 55, defects=0.25)
        from apps.reports.tasks import render_report

        render_report(str(b.id))
        b.refresh_from_db()
        return b

    @transaction.atomic
    def history(self, found: Booking, experts, days: int, per_day: int, inspected: int) -> None:
        """Copies of the finished original, written in bulk: bookings, inspections, file records,
        reports and the webhook log, as a server holds after `days` of use."""
        if Booking.objects.filter(booking_id__startswith=f"{PREFIX}H").exists() or days <= 0:
            return
        insp = Inspection.objects.filter(booking=found, status="submitted").first()
        assets = list(MediaAsset.objects.filter(booking=found))
        report = Report.objects.filter(booking=found).first()
        hooks = list(Integration.objects.filter(name__startswith="load test"))
        now = timezone.now()
        n = 0
        for day in range(days, 0, -1):
            when = now - timedelta(days=day)
            bookings, inspections, files, reports, deliveries = [], [], [], [], []
            for i in range(per_day):
                n += 1
                b = _fresh(found)
                b.booking_id = f"{PREFIX}H{n:06d}"
                b.created_at = when + timedelta(minutes=i * 3)
                b.inspection_date = when.date()
                b.assigned_expert = experts[n % len(experts)]
                done = i < inspected
                b.stage = "completed" if done else "cancelled"
                bookings.append(b)
                for h in hooks:
                    if h.event == "booking.created" or done:
                        deliveries.append(Delivery(integration=h, event=h.event, booking_id=b.id,
                                                   booking_uuid=str(b.id), booking_ref=b.booking_id,
                                                   status="success", attempts=1,
                                                   response_status=200, created_at=b.created_at,
                                                   last_attempt_at=b.created_at))
                if not done or insp is None:
                    continue
                c = _fresh(insp)
                c.booking_id, c.expert = b.id, b.assigned_expert
                inspections.append(c)
                for a in assets:
                    f = _fresh(a)
                    f.booking_id = b.id
                    f.created_at = f.verified_at = b.created_at
                    files.append(f)
                if report is not None:
                    r = copy.copy(report)
                    r.pk, r.booking_id, r.token = None, b.id, new_token()
                    r.generated_at = r.first_generated_at = b.created_at
                    reports.append(r)
            Booking.objects.bulk_create(bookings, batch_size=1000)
            Inspection.objects.bulk_create(inspections, batch_size=1000)
            MediaAsset.objects.bulk_create(files, batch_size=5000)
            Report.objects.bulk_create(reports, batch_size=1000)
            Delivery.objects.bulk_create(deliveries, batch_size=5000)
            self.stdout.write(f"history: {days - day + 1}/{days} days", ending="\r")
        self.stdout.write("")

    def today_bookings(self, ops, experts, n: int, unassigned: bool = False) -> list[dict]:
        """Today's work for the phones: booked and assigned (or, unassigned, left for the load
        script's Ops to give to a free phone), not started."""
        out = []
        bl = testdata.Builder({"ops": ops}, seed=13)
        day = timezone.localdate()
        for i in range(n):
            b = bl.booking(day, f"{9 + i % 11:02d}:00", self.form,
                           booking_id=f"{PREFIX}T{uuid.uuid4().hex[:10].upper()}")  # never twice
            if unassigned:
                out.append({"id": str(b.id), "ref": b.booking_id, "expert": None})
                continue
            expert = experts[i % len(experts)]
            services.assign(ops, b, expert.id)
            out.append({"id": str(b.id), "ref": b.booking_id, "expert": expert.username})
        return out

    def pdi_template(self, others: dict) -> tuple[dict, dict]:
        """Inspection answers with enough defects that the fields asking for files can hold 150
        photos and the videos; every file field of the form's own media is offered."""
        from apps.forms.models import Field

        version = testdata.live(self.form)
        extra = {f.key: f.type
                 for f in Field.objects.filter(version=version, key__startswith="lt_")}
        for seed in range(1, 60):
            defects = min(0.15 + seed * 0.02, 0.9)
            answers, asked = template(self.form, "inspection", others, defects, seed)
            for k, t in extra.items():           # the test form's extra page: always used
                asked[k] = t
                answers[k] = [f"@{t}"]
            plan = file_plan(version, asked, BIG_PHOTOS, self.videos)
            photos = sum(n for k, n in plan.items() if asked[k] == "photo")
            videos = sum(n for k, n in plan.items() if asked[k] == "video")
            if photos >= BIG_PHOTOS and videos >= self.videos:
                return answers, asked
        return answers, asked
