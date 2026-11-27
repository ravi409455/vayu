"""Test data for outside testers: a wiped server, the real setup, three tester logins and a small
team, and bookings for the last 3 days and today that cover every flow. Every booking made here
is "TST-…", so a later wipe can tell test data from real data. Answers are filled from each
form's own questions and rules: mostly fine, with a few problems, like a real day."""
import hashlib
import io
import random
import uuid
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management import call_command
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.bookings import activity, services, submissions, timing
from apps.bookings.models import Booking, Inspection
from apps.forms.models import Field, Form, MasterListItem, VersionStatus
from apps.forms.rules import truthy
from apps.media import storage
from apps.media.models import MediaAsset
from apps.media.services import check_completion

PREFIX = "TST-"
PHOTOS = Path(__file__).parent / "photos"     # stock car photos, when present (else drawn ones)
TESTERS = [("admin", Role.ADMIN, "Test Admin"), ("ops", Role.OPS, "Test Ops"),
           ("expert", Role.EXPERT, "Test Expert")]
TEAM = [("ops2", Role.OPS, "Rohan Mehta"), ("expert2", Role.EXPERT, "Suresh Patil"),
        ("expert3", Role.EXPERT, "Anjali Reddy"), ("expert4", Role.EXPERT, "Imran Sheikh"),
        ("expert5", Role.EXPERT, "Divya Nair"), ("expert6", Role.EXPERT, "Karthik Iyer"),
        ("expert7", Role.EXPERT, "Pooja Chauhan")]
CUSTOMERS = ["Aarav Kapoor", "Bhavna Rao", "Chetan Pawar", "Disha Malik", "Eshan Arora",
             "Fatima Syed", "Girish Nair", "Hema Pillai", "Irfan Mirza", "Jaya Kamat",
             "Kabir Sethi", "Leena Dsouza", "Mohan Rathi", "Nisha Gill", "Omkar Jadhav",
             "Preeti Saini", "Qasim Ali", "Radhika Iyer", "Sameer Dutta", "Trisha Bhat",
             "Uday Shetty", "Vandana Roy", "Waqar Hussain", "Yash Thakur", "Zoya Merchant",
             "Abhinav Joshi", "Bina Thomas", "Charu Verma", "Dev Anand", "Ekta Kapoor"]


class Guard(Exception):
    pass


# ---------------------------------------------------------------- safety

WIPEABLE = ("local", "test")


def stored_kind() -> str | None:
    """The kind of server this database belongs to, as setup_platform wrote it into it (F-213):
    a settings flag can be wrong for the database it points at; the database can't."""
    from apps.core.models import Setting

    value = Setting.objects.filter(key="server").values_list("value", flat=True).first()
    return (value or {}).get("kind")


def remember_kind() -> None:
    from apps.core.models import Setting

    if stored_kind() is None:
        Setting.objects.update_or_create(key="server", defaults={"value": {
            "kind": settings.SERVER_KIND, "name": settings.SERVER_NAME}})


def check_can_wipe(confirm: str) -> None:
    """The guards: a test or local server (by its settings and by what its database says), its
    name typed back, and no bookings that test data did not make."""
    kind = stored_kind()
    if settings.SERVER_KIND not in WIPEABLE or (kind is not None and kind not in WIPEABLE):
        raise Guard(f"This server is '{kind or settings.SERVER_KIND}'. Test data only goes on a "
                    "server set up with VAYU_SERVER_KIND=test (or local). Nothing was changed.")
    if not settings.SERVER_NAME or confirm != settings.SERVER_NAME:
        raise Guard("Type this server's name to confirm the wipe: --confirm "
                    f"{settings.SERVER_NAME or '<VAYU_SERVER_NAME is not set>'}. "
                    "Nothing was changed.")
    real = Booking.objects.exclude(booking_id__startswith=PREFIX)
    if real.exists():                                     # on every kind of server (F-213)
        example = real.first()
        raise Guard(f"{real.count()} bookings here were not made by the test data "
                    f"(e.g. {example.booking_id if example else '?'}). They may be real: nothing "
                    "was wiped.")


def wipe() -> None:
    """Empty the database and the file store, then put back what migrations seeded."""
    call_command("flush", interactive=False, verbosity=0)
    client = storage.client()
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=settings.S3_BUCKET):
        for o in page.get("Contents", []):
            client.delete_object(Bucket=settings.S3_BUCKET, Key=o["Key"])
    from apps.accounts.catalog import DEFAULTS
    from apps.accounts.models import RolePermission

    for role, grants in DEFAULTS.items():
        for key, scope in grants.items():
            RolePermission.objects.get_or_create(role=role, permission=key,
                                                 defaults={"scope": scope})
    remember_kind()


def make_users(password: str) -> dict[str, User]:
    out = {}
    for n, (username, role, name) in enumerate([*TESTERS, *TEAM]):
        u = User.objects.create_user(username=username, password=password, role=role, name=name,
                                     phone=f"98000000{n:02d}", must_change_password=False)
        out[username] = u
    return out


# ---------------------------------------------------------------- pictures

PAYMENT_NOTE = "PAYMENT SCREENSHOT"


def _payment_picture(caption: str) -> bytes:
    """A payment screenshot nobody can miss: red, with its name, so a tester sees at once when
    one reaches a report or a customer's download (it never should)."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (640, 480), (200, 20, 30))
    d = ImageDraw.Draw(img)
    d.rectangle((20, 20, 620, 460), outline=(255, 255, 255), width=8)
    for y, line in ((150, PAYMENT_NOTE), (210, "NOT FOR THE CUSTOMER"), (270, caption[:60])):
        d.text((60, y), line, fill=(255, 255, 255), font_size=40)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=72)
    return buf.getvalue()


def _picture(caption: str, n: int, field_key: str = "") -> bytes:
    if "payment" in field_key:
        return _payment_picture(caption)
    files = sorted(PHOTOS.glob("*.jpg")) if PHOTOS.exists() else []
    if files:
        return files[n % len(files)].read_bytes()
    from PIL import Image, ImageDraw

    shade = 80 + (n * 37) % 120
    img = Image.new("RGB", (640, 480), (shade, shade + 12, shade + 30))
    d = ImageDraw.Draw(img)
    d.rectangle((120, 220, 520, 330), fill=(40, 44, 52))           # a car-ish shape
    d.ellipse((160, 300, 240, 380), fill=(20, 20, 20))
    d.ellipse((400, 300, 480, 380), fill=(20, 20, 20))
    d.text((20, 20), caption[:60], fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=72)
    return buf.getvalue()


class Pictures:
    def __init__(self):
        self.n = 0

    def add(self, booking: Booking, who: User, field_key: str, caption: str,
            kind: str = "photo") -> str:
        """A verified file on the booking, as if the phone had sent it."""
        self.n += 1
        data = (_picture(caption, self.n, field_key) if kind == "photo"
                else b"\x00\x00\x00\x18ftypmp42")
        ctype = "image/jpeg" if kind == "photo" else "video/mp4"
        a = MediaAsset(client_uuid=uuid.uuid4(), booking=booking, uploaded_by=who,
                       field_key=field_key, kind=kind, content_type=ctype, size=len(data),
                       sha256=hashlib.sha256(data).hexdigest(), status="verified",
                       verified_at=timezone.now())
        a.key = f"bookings/{booking.id}/{a.id}"
        storage.put(a.key, data, ctype)
        a.save()
        return str(a.id)


# ---------------------------------------------------------------- answers

TEXT = {"registration": "MH12AB1234", "variant": "VXI", "colour": "Pearl White",
        "city": "Pune", "year": "2022"}


def _text(label: str, rng: random.Random) -> str:
    low = label.lower()
    for word, value in TEXT.items():
        if word in low:
            return value
    if "chassis" in low:
        return "MA3" + "".join(rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ0123456789") for _ in range(14))
    if "engine" in low and "number" in low:
        return "K12N" + str(rng.randint(1000000, 9999999))
    return "Ok"


def fill(version, ns: str, booking: Booking | None, who: User | None, rng: random.Random,
         pics: Pictures | None, *, defects: float = 0.0, others: dict | None = None,
         overrides: dict | None = None) -> dict:
    """Answers for every field the form would show, following its own rules: the fine answer of
    each check, a problem now and then (`defects`), a picture for each photo asked for."""
    overrides = overrides or {}
    answers: dict[str, Any] = {}
    fields = list(Field.objects.filter(version=version).select_related("section", "section__page")
                  .order_by("section__page__order", "section__order", "order", "id"))
    # twice: a question may come before the answer that decides whether it is asked
    for f in fields + [f for f in fields]:
        if f.key in answers:
            continue
        data = {**(others or {}), ns: answers, "_today": timezone.localdate().isoformat(),
                "_defects": []}
        if not truthy(f.section.show_if, data) or not truthy(f.show_if, data):
            continue
        if ((f.section.access or {}).get("expert") or {}).get("in_progress") == "hidden":
            continue                                   # Ops' own page: never the expert's
        if f.key in overrides:
            answers[f.key] = overrides[f.key]
            continue
        t, c = f.type, f.config or {}
        if t in ("rating", "derived", "image", "form_choice", "user_picker"):
            continue
        if t in ("single_choice", "multi_choice"):
            opts = c.get("options", [])
            if not opts:
                continue
            fine = [o for o in opts if o.get("tone") == "ok"] or opts
            bad = [o for o in opts if o.get("is_defect")]
            pick = rng.choice(bad) if bad and rng.random() < defects else fine[0]
            answers[f.key] = [pick["key"]] if t == "multi_choice" else pick["key"]
        elif t == "number":
            lo, hi = c.get("min", 1), c.get("max")
            answers[f.key] = int(hi) if hi is not None and hi < 10 else max(int(lo), 2)
        elif t == "currency":
            answers[f.key] = 1500
        elif t in ("short_text", "phone"):
            if t == "phone":
                answers[f.key] = "9876543210"
            elif c.get("pattern") == r"^\d+$":
                answers[f.key] = str(rng.randint(1022, 4825))        # e.g. a tyre's week+year
            else:
                answers[f.key] = _text(f.label, rng)
        elif t == "long_text":
            answers[f.key] = "No major issues found." if not defects else \
                "Minor issues noted; see the photos."
        elif t == "date":
            answers[f.key] = timezone.localdate().isoformat()
        elif t == "time":
            answers[f.key] = "10:30"
        elif t == "datetime":
            answers[f.key] = timezone.localtime().isoformat(timespec="minutes")
        elif t == "gps":
            answers[f.key] = {"lat": 18.5204 + rng.random() / 100, "lng": 73.8567, "accuracy": 8}
        elif t == "yes_no":
            answers[f.key] = False
        elif t == "master_list":
            item = MasterListItem.objects.filter(list__key=c.get("list"),
                                                 archived=False).order_by("order").first()
            if item:
                answers[f.key] = item.key
        elif t in ("photo", "video") and pics and booking and who and (
                f.required or f.show_if or rng.random() < 0.5):
            n = 1 if t == "video" else min(c.get("max_count", 1), 2)
            answers[f.key] = [pics.add(booking, who, f.key, f.label, t) for _ in range(n)]
    return answers


def live(form_key: str):
    form = Form.objects.get(key=form_key)
    return form.versions.filter(status=VersionStatus.PUBLISHED).order_by("-number").first()


# ---------------------------------------------------------------- bookings

class Builder:
    def __init__(self, users: dict[str, User], seed: int = 7):
        self.u = users
        self.ops = users["ops"]
        self.rng = random.Random(seed)  # noqa: S311 - seeded test data, not security
        self.pics = Pictures()
        self.n = 0
        self.cities = list(MasterListItem.objects.filter(list__key="city", archived=False)
                           .values_list("key", flat=True)[:6])
        self.cars = list(MasterListItem.objects.filter(list__key="car_make_model",
                                                       archived=False)
                         .values_list("key", flat=True)[:40])

    def booking(self, day, at: str, itype: str, **extra) -> Booking:
        self.n += 1
        ref = f"{PREFIX}{1000 + self.n}"
        city = self.cities[self.n % len(self.cities)]
        answers = fill(live("booking"), "booking", None, None, self.rng, None, overrides={
            "booking_id": ref, "customer_name": CUSTOMERS[self.n % len(CUSTOMERS)],
            "customer_phone": f"98765{30000 + self.n}", "address": f"{ref}, MG Road",
            "city": city, "car_make_model": self.cars[self.n % len(self.cars)],
            "inspection_type": itype, "inspection_date": day.isoformat(),
            "inspection_time": at, **extra})
        return services.create(self.ops, answers)

    def _start_answers(self, b, expert):
        return fill(live("start"), "start", b, expert, self.rng, self.pics)

    def start(self, b: Booking, expert: User) -> dict:
        services.assign(self.ops, b, expert.id) if b.assigned_expert_id != expert.id else None
        start = self._start_answers(b, expert)
        submissions.start(expert, b, uuid.uuid4(), None, b.inspection_type, None, start)
        b.refresh_from_db()
        return start

    def submit(self, b: Booking, expert: User, start: dict, *, defects=0.08,
               overrides=None, hold: tuple[str, ...] = (), paid: bool = False) -> None:
        """hold: "optional" / "required" keeps one such photo field's files from arriving, so
        the job waits for files (Ops finish it, or upload the required one first)."""
        others = {"booking": b.answers, "start": start}
        if paid:       # a late start paid by UPI, and a payment at the wrap-up: two screenshots
            overrides = {"inspection_45_minutes_delayed": "yes", "delay_payment_mode": "upi",
                         **(overrides or {})}
        version = live(b.inspection_type)
        insp = fill(version, "inspection", b, expert, self.rng, self.pics,
                    defects=defects, others=others, overrides=overrides)
        end = fill(live("end"), "end", b, expert, self.rng, self.pics, overrides={
            "taking_payment": True, "payment_mode": "upi"} if paid else None)
        for want in hold:
            f = next((f for f in Field.objects.filter(version=version, type="photo")
                      .order_by("order") if insp.get(f.key)
                      and (f.required and not f.required_if) == (want == "required")), None)
            if f is None and want == "optional":     # none answered by chance: answer one
                f = next((x for x in Field.objects.filter(version=version, type="photo")
                          .order_by("order") if not x.required and not x.show_if), None)
                if f is not None:
                    insp[f.key] = [self.pics.add(b, expert, f.key, f.label)]
            if f is not None:
                MediaAsset.objects.filter(id__in=insp[f.key]).update(status="uploading")
        submissions.submit(expert, b, uuid.uuid4(), {"inspection": insp, "start": start,
                                                     "end": end})
        check_completion(b.id)

    def done(self, b: Booking, expert: User, began, minutes: int, **kw) -> Booking:
        """A finished inspection that began at `began` and took `minutes`."""
        start = self.start(b, expert)
        self.submit(b, expert, start, **kw)
        b.refresh_from_db()
        Inspection.objects.filter(booking=b, status="submitted").update(
            submitted_at=began + timedelta(minutes=minutes))
        b.started_at = began
        timing.stamp_late(b)
        timing.stamp_duration(b, began + timedelta(minutes=minutes))
        b.save(update_fields=["started_at", "late_minutes", "duration_minutes"])
        return b


def at_hour(day, hour: float):
    now = timezone.localtime()
    base = datetime.combine(day, time(0), tzinfo=now.tzinfo)
    return base + timedelta(hours=hour)


def hhmm(hour: float) -> str:
    m = max(0, min(23 * 60 + 30, round(hour * 12) * 5))
    return f"{m // 60:02d}:{m % 60:02d}"


TYPES = ["pdi", "used_car", "ev"]


def field_tour(admin) -> None:
    """The Field tour form (every field type once, demo_forms): test servers only. Publishing it
    adds "Field tour" to the booking's inspection types."""
    from apps.platform import demo_forms

    from . import reports

    demo_forms.build_field_tour(admin, reports.brand(admin)[0])


def build_days(bl: Builder) -> dict[str, list[str]]:
    """The scenarios. Returns {what: [booking refs]} for the summary."""
    u, today = bl.u, timezone.localdate()
    now_h = timezone.localtime().hour + timezone.localtime().minute / 60
    out: dict[str, list[str]] = {}

    def note(what, b):
        out.setdefault(what, []).append(b.booking_id)
        return b

    experts = [u[k] for k in ("expert", "expert2", "expert3", "expert4", "expert5", "expert6")]
    # ---- last 3 days: finished inspections with PDFs, some reviewed by Ops
    for back in (3, 2, 1):
        day = today - timedelta(days=back)
        for k in range(4):
            itype = TYPES[(back + k) % 3]
            b = bl.booking(day, hhmm(9.5 + 2 * k), itype)
            e = experts[(back + k) % len(experts)]
            services.assign(bl.ops, b, e.id)
            note(f"completed {back} day(s) ago", bl.done(
                b, e, at_hour(day, 9.5 + 2 * k + (0.6 if k == 1 else 0)), 70 + 10 * k,
                defects=0.12 if k % 2 else 0.04,
                paid=back == 3 and k < 3))            # the first of each type took payments
    # ---- today: the tester expert's day
    me = u["expert"]
    b = bl.booking(today, hhmm(max(8, now_h - 4)), "pdi")
    services.assign(bl.ops, b, me.id)
    note("expert: done today", bl.done(b, me, at_hour(today, max(8, now_h - 4)), 75))
    b = bl.booking(today, hhmm(max(8, now_h - 0.5)), "used_car")
    services.assign(bl.ops, b, me.id)
    bl.start(b, me)
    note("expert: in progress", b)
    for off, itype in ((1.5, "ev"), (3.5, "pdi")):
        b = bl.booking(today, hhmm(min(22, now_h + off)), itype)
        services.assign(bl.ops, b, me.id)
        note("expert: to start", b)
    for off, itype in ((1, "used_car"),):
        b = bl.booking(today + timedelta(days=1), hhmm(10 + off), itype)
        services.assign(bl.ops, b, me.id)
        note("expert: tomorrow", b)
    if Form.objects.filter(key="tour").exists():
        b = bl.booking(today, hhmm(min(22, now_h + 0.5)), "tour")
        services.assign(bl.ops, b, me.id)
        note("expert: field tour (every field type)", b)
    # ---- today: Ops' queue
    for off, itype in ((1, "pdi"), (2.5, "used_car"), (4, "ev")):
        note("ops: unassigned today", bl.booking(today, hhmm(min(22, now_h + off)), itype))
    b = bl.booking(today, hhmm(min(22, now_h + 2)), "pdi")
    services.assign(bl.ops, b, u["expert3"].id)
    services.reschedule(bl.ops, b, (today + timedelta(days=2)).isoformat(), "11:00",
                        "customer_request")
    note("ops: rescheduled", b)
    b = bl.booking(today, hhmm(min(22, now_h + 3)), "ev")
    services.assign(bl.ops, b, u["expert4"].id)
    services.cancel(bl.ops, b, "customer_cancelled")
    note("ops: cancelled", b)
    b = bl.booking(today, hhmm(max(8, now_h - 1)), "pdi")
    services.assign(bl.ops, b, u["expert5"].id)
    services.change_type(bl.ops, b, "used_car")
    submissions.start(u["expert5"], b, uuid.uuid4(), None, "pdi", None,
                      bl._start_answers(b, u["expert5"]))
    note("ops: type change rejected", b)
    b = bl.booking(today, hhmm(max(8, now_h - 3)), "used_car")
    services.assign(bl.ops, b, u["expert2"].id)
    s1 = bl.start(b, u["expert2"])
    services.force_release(bl.ops, b)
    services.assign(bl.ops, b, u["expert6"].id)
    s2 = bl.start(b, u["expert6"])
    bl.submit(b, u["expert6"], s2)
    bl.submit(b, u["expert2"], s1)
    note("ops: conflict (two experts)", b)
    b = bl.booking(today, hhmm(max(8, now_h - 2)), "ev")
    services.assign(bl.ops, b, u["expert3"].id)
    bl.start(b, u["expert3"])
    stuck = MediaAsset(client_uuid=uuid.uuid4(), booking=b, uploaded_by=u["expert3"],
                       field_key="selfie", kind="photo", content_type="image/jpeg", size=250_000,
                       sha256=hashlib.sha256(b"stuck").hexdigest(), status="uploading")
    stuck.key = f"bookings/{b.id}/{stuck.id}"
    stuck.save()
    MediaAsset.objects.filter(pk=stuck.pk).update(created_at=timezone.now() - timedelta(hours=9))
    note("ops: stuck upload", b)
    b = bl.booking(today, hhmm(max(8, now_h - 2.5)), "pdi")
    services.assign(bl.ops, b, u["expert5"].id)
    bl.submit(b, u["expert5"], bl.start(b, u["expert5"]), hold=("optional",))
    note("ops: waiting for files (can finish)", b)
    b = bl.booking(today, hhmm(max(8, now_h - 2.5)), "used_car")
    services.assign(bl.ops, b, u["expert7"].id)
    bl.submit(b, u["expert7"], bl.start(b, u["expert7"]), hold=("optional", "required"))
    note("ops: waiting for files (required one missing)", b)
    b = bl.booking(today, hhmm(max(8, now_h - 5)), "pdi")
    services.assign(bl.ops, b, u["expert4"].id)
    note("ops: started late", bl.done(b, u["expert4"], at_hour(today, max(8, now_h - 5) + 0.75),
                                      70))
    b = bl.booking(today, hhmm(max(8, now_h - 6)), "used_car")
    services.assign(bl.ops, b, u["expert6"].id)
    note("ops: too quick", bl.done(b, u["expert6"], at_hour(today, max(8, now_h - 6)), 12))
    return out


def ops_review(bl: Builder, refs: list[str]) -> None:
    """Ops' work on finished inspections: a Key Check typed over, a rating overridden, a photo
    replaced (the old one kept as history) and reports downloaded and shared."""
    u = bl.u
    for n, ref in enumerate(refs[:4]):
        b = Booking.objects.get(booking_id=ref)
        insp = Inspection.objects.filter(booking=b, status="submitted").first()
        if insp is None:
            continue
        version = insp.form_version
        body: dict[str, Any] = {}
        checks = [kc["key"] for kc in version.key_checks or []]
        if checks:
            body["key_checks"] = {checks[0]: "Checked with the owner: none"}
        cats = [c["key"] for c in (version.rating_config or {}).get("categories", [])]
        if cats and n % 2 == 0:
            body["ratings"] = {cats[0]: 4}
        if body:
            submissions.set_overrides(u["ops"], insp, body, insp.row_version)
        if n < 2 and Field.objects.filter(version=version, key="key_check_1_label").exists():
            insp.refresh_from_db()                 # Ops' own page: a comment and named checks
            mine = {"expert_comments": "Clean car overall. Minor marks noted; see the photos.",
                    "key_check_1_label": "Service history",
                    "key_check_1_value": "Verified, 3 services",
                    "key_check_2_label": "Second key", "key_check_2_value": "Available"}
            if b.inspection_type == "used_car":       # the price and the service centre's record
                mine.update(price_estimate="₹ 12,50,000 - ₹ 13,50,000",
                            last_service_date="12-08-2026", total_services="6",
                            last_odometer_reading="36,400 km",
                            service_history_analysis="Serviced on time at the authorised centre.")
            else:
                mine["manufacturing_date"] = "March 2026"
            submissions.edit_inspection(u["ops"], insp, {"inspection": mine}, insp.row_version)
        activity.log(b, u["ops"], "report_downloaded", {"revision": 1})
        if n == 0:
            activity.log(b, u["admin"], "report_shared", {"revision": 1, "how": "check_link"})


def admin_bits(admin: User) -> list[str]:
    """Things for the Admin tester to look at: a draft form version and a webhook with
    deliveries."""
    from apps.forms import services as form_services
    from apps.integrations.models import Delivery, Integration

    made = []
    form_services.create_draft(admin, Form.objects.get(key="ev"))
    made.append("EV form: a draft version to edit and publish")
    pdi = Form.objects.get(key="pdi")
    hook = Integration.objects.create(form=pdi, name="Partner: PDF ready", event="pdf.ready",
                                      url="https://example.invalid/hook", include_data=True,
                                      include_pdf=True, created_by=admin)
    now = timezone.now()
    for n, b in enumerate(Booking.objects.filter(stage="completed")[:3]):
        Delivery.objects.create(integration=hook, event=hook.event, booking=b,
                                booking_uuid=str(b.id), booking_ref=b.booking_id,
                                status=("success", "failed", "retrying")[n], attempts=n + 1,
                                response_status=(200, 404, 503)[n],
                                last_attempt_at=now - timedelta(minutes=20 * (n + 1)))
    made.append("Integration 'Partner: PDF ready' with 3 deliveries")
    return made
