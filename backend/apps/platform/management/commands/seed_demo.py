"""Local review only: three users, the booking / check-in / PDI forms and a PDF template, and a
few bookings in different states, so every screen has something to look at.

The inspection forms (PDI, Used car, EV...) are meant to be built by hand in the form builder;
the PDI form here is the full one from the sample report (apps/core/demo_pdi.py), so the flow and
the report can be tried straight away."""
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.bookings import services, submissions, timing
from apps.bookings.models import Booking
from apps.forms import services as form_services
from apps.forms.models import (
    Field,
    Form,
    FormVersion,
    MasterList,
    MasterListItem,
    Page,
    Section,
)
from apps.media.services import check_completion

PASSWORD = "Vayu-local-1"
ALLOWED = ("vayu.settings.local", "vayu.settings.test", "vayu.settings.e2e")
USERS = [("admin", Role.ADMIN, "Asha Admin", False), ("ops", Role.OPS, "Priya Ops", False),
         ("expert", Role.EXPERT, "Ravi Expert", False),
         ("expert2", Role.EXPERT, "Meera Expert", False),
         ("newuser", Role.OPS, "Nina New (must change password)", True),
         ("ops2", Role.OPS, "Rohan Ops", False),
         *[(f"expert{n}", Role.EXPERT, name, False) for n, name in enumerate((
             "Suresh Patil", "Anjali Reddy", "Imran Sheikh", "Divya Nair", "Karthik Iyer",
             "Pooja Chauhan", "Vivek Joshi", "Neelam Singh", "Rahul Bansal", "Sana Qureshi",
             "Harish Gupta", "Lakshmi Menon", "Aditya Kulkarni", "Farah Khan", "Manish Yadav",
             "Tara Bose", "Gaurav Mishra", "Isha Deshmukh"), start=3)]]
LISTS = {"city": [("delhi", "Delhi"), ("pune", "Pune"), ("mumbai", "Mumbai")],
         "car_make_model": [("maruti_victoris", "Maruti Victoris"), ("tata_nexon", "Tata Nexon"),
                            ("hyundai_creta", "Hyundai Creta"),
                            ("mahindra_xuv_3xo", "Mahindra XUV 3XO AX5")]}


def _publish(form: Form) -> FormVersion:
    draft = form.versions.filter(status="draft").first()
    assert draft is not None
    return form_services.publish_version(User.objects.get(username="admin"), draft.id,
                                         draft.row_version)


def _field(version, section, key, label, type_, **kw) -> Field:
    config = kw.pop("config", {})
    return Field.objects.create(version=version, section=section, key=key, label=label,
                                type=type_, order=section.fields.count(), config=config, **kw)


class Command(BaseCommand):
    help = "Create demo users, forms and bookings for local review."

    def add_arguments(self, parser):
        parser.add_argument("--if-empty", action="store_true",
                            help="do nothing (no error) when the demo data is already there")
        parser.add_argument("--no-today", action="store_true",
                            help="leave out today's busy schedule (it is slow: tests use this)")

    def handle(self, *args, if_empty=False, no_today=False, **options):
        if settings.SETTINGS_MODULE not in ALLOWED:
            raise CommandError("seed_demo only runs with local, test or e2e settings.")
        if User.objects.filter(username="admin").exists():
            if if_empty:
                self.stdout.write("Demo data is already there.")
                return
            raise CommandError("Demo data already exists. Run `scripts/local.sh reset` first.")
        call_command("seed_master_lists", verbosity=0)
        for key, items in LISTS.items():
            lst = MasterList.objects.get(key=key)
            for n, (k, label) in enumerate(items):
                MasterListItem.objects.get_or_create(list=lst, key=k,
                                                     defaults={"label": label, "order": n})
        for username, role, name, must in USERS:
            User.objects.create_user(username=username, password=PASSWORD, role=role, name=name,
                                     must_change_password=must)
        User.objects.filter(username="expert").update(phone="+919876500111")  # for the profile
        admin = User.objects.get(username="admin")
        form_services.ensure_system_forms()
        _publish(Form.objects.get(type="booking"))
        self._system_forms(admin)
        self._inspection_forms(admin)
        self._bookings()
        self._more_bookings()
        if not no_today:
            self._today()
        self._integrations(admin)
        self.stdout.write(self.style.SUCCESS(
            f"Demo ready. Sign in as admin / ops / expert / expert2 with password {PASSWORD}"))

    def _system_forms(self, admin):
        """The start (check-in) and end (wrap-up) forms come with their locked fields; add a few
        custom ones and a payment QR picture to the end form."""
        import io

        from PIL import Image

        from apps.forms import assets

        _publish(Form.objects.get(type="start"))
        form = Form.objects.get(type="end")
        v = form.versions.get(status="draft")
        pay = Section.objects.get(version=v, title="Payment")
        paid = {"==": [{"var": "end.taking_payment"}, True]}
        qr = Image.new("RGB", (25, 25), "white")
        for x in range(25):
            for y in range(25):
                if (x * 7 + y * 13 + x * y) % 3 == 0:
                    qr.putpixel((x, y), (0, 0, 0))
        buf = io.BytesIO()
        qr.resize((250, 250), Image.Resampling.NEAREST).save(buf, "PNG")
        asset = assets.create_asset(admin, buf.getvalue())
        _field(v, pay, "pay_qr", "Scan to pay", "image", show_if=paid,
               config={"asset": str(asset.id)})
        wrap = Page.objects.get(version=v)
        review = Section.objects.create(version=v, page=wrap, title="Review", order=1)
        _field(v, review, "google_review", "Google review taken", "yes_no")
        shot = {"==": [{"var": "end.google_review"}, True]}
        _field(v, review, "review_screenshot", "Review screenshot", "photo", show_if=shot,
               config={"max_count": 1})
        _field(v, review, "perfume_given", "Car perfume given", "yes_no")
        _publish(form)

    def _inspection_forms(self, admin):
        from apps.platform import demo_forms as d
        from apps.platform import demo_pdi
        from apps.reports import service as reports

        d.library_items(admin)
        form, _ = demo_pdi.build_pdi(admin)
        template = reports.create_template(admin, form)
        draft = template.versions.get(status="draft")
        logo, mark = self._brand_assets(admin)
        disclaimer = (Path(demo_pdi.__file__).parent / "seed_assets" / "pdi-disclaimer.html")
        definition = demo_pdi.pdf_definition(str(logo.id), str(mark.id),
                                             disclaimer.read_text())
        definition = self._shared(admin, definition)
        d.build_field_tour(admin, str(logo.id))     # every field type once, to try the app
        saved = reports.save_definition(admin, draft, definition, draft.row_version)
        reports.publish(admin, saved, saved.row_version)
        for key, name, itype, pages, code, title in (
                ("used_car", "Used car", "used_car", d.used_pages(), "UC",
                 "USED CAR INSPECTION REPORT"),
                ("ev", "EV", "ev", d.ev_pages(), "EV", "ELECTRIC CAR INSPECTION REPORT")):
            form, _ = d.build_inspection(admin, key=key, name=name, itype=itype, pages=pages)
            template = reports.create_template(admin, form)
            draft = template.versions.get(status="draft")
            definition = d.pdf_definition(code, title, form)
            saved = reports.save_definition(admin, draft, definition, draft.row_version)
            reports.publish(admin, saved, saved.row_version)

    def _shared(self, admin, definition: dict) -> dict:
        """The Car C.I.D. look and the disclaimer as shared items (themes and shared parts are
        edited once for every template that uses them)."""
        from apps.reports import shared

        theme = {k: definition.pop(k) for k in shared.THEME_KEYS if k in definition}
        item, _ = shared.save(admin, "theme", "carcid", "Car C.I.D.", theme)
        definition["theme_ref"] = {"key": "carcid", "revision": item.revision}
        page = next(p for p in definition["pages"] if p["title"] == "Disclaimer")
        item, _ = shared.save(admin, "snippet", "pdi_disclaimer", "PDI disclaimer",
                              {"parts": page["parts"]})
        page["parts"] = [{"type": "snippet", "ref": {"key": "pdi_disclaimer",
                                                     "revision": item.revision}}]
        return definition

    def _brand_assets(self, admin):
        """The Car C.I.D. logo and the faint shield watermark, as uploaded pictures."""
        import io

        from PIL import Image

        from apps.forms import assets

        folder = Path(__file__).resolve().parents[2] / "seed_assets"
        out = []
        for name, edge in (("carcid-logo.webp", 400), ("carcid-watermark.webp", 900)):
            img = Image.open(folder / name).convert("RGBA")
            img.thumbnail((edge, edge))
            buf = io.BytesIO()
            img.save(buf, "PNG", optimize=True)
            label = "Car C.I.D. logo" if "logo" in name else "Car C.I.D. watermark"
            out.append(assets.create_asset(admin, buf.getvalue(), label))
        return out

    def _selfie(self, booking, expert) -> str:
        """A real (tiny) verified picture, so the completed demo booking has its selfie."""
        return self._photo(booking, expert, "selfie", "Selfie")

    def _photo(self, booking, expert, field_key: str, caption: str) -> str:
        """A small verified picture with its caption written on it."""
        import hashlib
        import io

        from PIL import Image, ImageDraw

        from apps.media import storage
        from apps.media.models import MediaAsset

        shade = 90 + (sum(map(ord, field_key)) % 90)
        img = Image.new("RGB", (320, 240), (shade, shade + 10, shade + 25))
        ImageDraw.Draw(img).text((12, 108), caption[:48], fill=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=70)
        data = buf.getvalue()
        a = MediaAsset(client_uuid=uuid.uuid4(), booking=booking, uploaded_by=expert,
                       field_key=field_key, kind="photo", content_type="image/jpeg",
                       size=len(data), sha256=hashlib.sha256(data).hexdigest(), status="verified")
        a.key = f"bookings/{booking.id}/{a.id}"
        storage.put(a.key, data, "image/jpeg")
        a.save()
        return str(a.id)

    def _bookings(self):
        ops = User.objects.get(username="ops")
        expert = User.objects.get(username="expert")
        base = {"customer_phone": "9876500000", "inspection_type": "pdi",
                "inspection_time": "10:30"}

        def make(ref, name, city, car, day):
            return services.create(ops, {**base, "booking_id": ref, "customer_name": name,
                                         "address": f"{ref} demo street, {city.title()}",
                                         "city": city, "car_make_model": car,
                                         "inspection_date": day})

        make("DEMO-1", "Kavya Rao", "delhi", "maruti_victoris", "2026-12-01")
        b2 = make("DEMO-2", "Arjun Mehta", "pune", "tata_nexon", "2026-12-01")
        services.assign(ops, b2, expert.id)
        b3 = make("DEMO-3", "Sunita Iyer", "delhi", "mahindra_xuv_3xo",
                  "2026-11-24")
        services.assign(ops, b3, expert.id)
        selfie = self._selfie(b3, expert)          # the check-in selfie: the job starts with it
        submissions.start(expert, b3, uuid.uuid4(), None, "pdi", None, {"selfie": [selfie]})
        b3.refresh_from_db()
        submissions.submit(expert, b3, uuid.uuid4(), {   # the sample report AV66022, in full
            "inspection": self._pdi_answers(b3, expert, "MA1NS2NP1T2H75335", 39),
            "start": {"selfie": [selfie]}, "end": {"taking_payment": False}})
        check_completion(b3.id)        # Completed: the PDF is made by the worker
        # a short job with every field type, for trying the app quickly
        tour = services.create(ops, {
            **base, "booking_id": "DEMO-90", "customer_name": "Neha Kapoor",
            "address": "DEMO-90 demo street, Pune", "city": "pune",
            "car_make_model": "hyundai_creta", "inspection_type": "tour",
            "inspection_date": str(timezone.localdate()), "inspection_time": "12:00"})
        services.assign(ops, tour, expert.id)


    # ---------------------------------------------------------------- more bookings and problems

    def _pending_asset(self, booking, expert, field_key, status, days_old):
        """A photo the phone never finished sending: it makes a 'stuck upload' problem."""
        import hashlib

        from apps.media.models import MediaAsset

        a = MediaAsset(client_uuid=uuid.uuid4(), booking=booking, uploaded_by=expert,
                       field_key=field_key, kind="photo", content_type="image/jpeg", size=250_000,
                       sha256=hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest(), status=status)
        a.key = f"bookings/{booking.id}/{a.id}"
        a.save()
        MediaAsset.objects.filter(pk=a.pk).update(
            created_at=timezone.now() - timedelta(days=days_old))
        return str(a.id)

    def _pdi_answers(self, booking, expert, chassis, odometer, **overrides):
        """Every check answered like the sample report, with a picture for every photo needed."""
        from apps.platform.demo_pdi import sample_answers

        version = Form.objects.get(key="pdi").versions.get(status="published")
        answers, photos = sample_answers(version, chassis, odometer=odometer, **overrides)
        labels = dict(Field.objects.filter(version=version).values_list("key", "label"))
        for key in photos:
            answers[key] = [self._photo(booking, expert, key, labels[key])]
        return answers

    # the same values for the Used car and EV forms; anything not listed gets a sensible default
    _VALUES: dict[str, Any] = {
        "registration_no": "MH12AB1234", "colour": "Pearl white", "make_year": 2022, "keys": 2,
        "owner_count": 1, "owners": 1, "city_used": "Pune", "paint_thickness": 120,
        "soh": 91, "range_claim": 380, "ac_temp": 8, "fuel": "petrol", "transmission": "manual",
        "service_book": True, "rc_book": True, "insurance": True, "puc": True,
        "fast_charge_ok": True, "door_fl": "minor",
        "remarks": "Clean car, one minor dent on the front left door. Ready to buy."}

    def _form_answers(self, booking, expert, key: str, km: int, **overrides) -> dict:
        """Answers for a Used car or EV form: every visible field filled, a picture for every
        photo that is always shown (the view photos) and for every required one."""
        from apps.forms.rules import truthy

        version = Form.objects.get(key=key).versions.get(status="published")
        values = {**self._VALUES, "odometer": km, **overrides}
        answers: dict = {"chassis_no": f"MA3{key.upper()[:3]}0000{booking.booking_id[-2:]}"}
        fields = (Field.objects.filter(version=version).select_related("section")
                  .order_by("section__page__order", "section__order", "order"))
        for f in fields:
            data = {"inspection": answers}
            if not truthy(f.show_if, data) or not truthy(f.section.show_if, data):
                continue
            if f.key in values:
                answers[f.key] = values[f.key]
            elif f.type == "single_choice":
                answers[f.key] = f.config["options"][0]["key"]
            elif f.type == "number":
                answers[f.key] = max(f.config.get("min", 0), 6)
            elif f.type == "yes_no":
                answers[f.key] = False
            elif f.type == "photo" and f.key.startswith("photo_"):
                answers[f.key] = [self._photo(booking, expert, f.key, f.label)]
        return answers

    def _more_bookings(self):
        """Bookings in every stage, plus the situations that fill the Problems page."""
        ops = User.objects.get(username="ops")
        e1, e2 = User.objects.get(username="expert"), User.objects.get(username="expert2")
        base = {"inspection_time": "10:30"}
        phones = iter(["9876501001", "9876501002", "9876501003", "9876501004", "9876501005",
                       "9876501006", "9876501007", "9876501008", "9876501009", "9876501010",
                       "9876501011", "9876501012", "9876501013", "9876501014", "9876501015"])

        def make(ref, name, city, car, day, itype="pdi", at="10:30"):
            return services.create(ops, {**base, "inspection_time": at, "booking_id": ref,
                                         "customer_name": name, "customer_phone": next(phones),
                                         "address": f"{ref} lane, {city.title()}", "city": city,
                                         "car_make_model": car, "inspection_date": day,
                                         "inspection_type": itype})

        def start(b, expert, itype="pdi"):
            selfie = self._selfie(b, expert)       # a job only starts once the check-in is done
            submissions.start(expert, b, uuid.uuid4(), None, itype, None, {"selfie": [selfie]})
            b.refresh_from_db()
            return selfie

        def submit(b, expert, chassis, km, **overrides):
            selfie = self._selfie(b, expert)
            submissions.submit(expert, b, uuid.uuid4(), {
                "inspection": self._pdi_answers(b, expert, chassis, km, **overrides),
                "start": {"selfie": [selfie]}, "end": {"taking_payment": False}})

        # waiting to be assigned
        make("DEMO-4", "Rohit Sharma", "delhi", "hyundai_creta", "2026-12-02", "ev")
        make("DEMO-5", "Pooja Nair", "mumbai", "tata_nexon", "2026-12-03", "used_car", "14:00")
        # assigned (one of them rescheduled once)
        b = make("DEMO-6", "Vikram Singh", "pune", "maruti_victoris", "2026-12-02", at="09:00")
        services.assign(ops, b, e2.id)
        b = make("DEMO-7", "Anita Desai", "mumbai", "hyundai_creta", "2026-12-02", "used_car")
        services.assign(ops, b, e1.id)
        services.reschedule(ops, b, "2026-12-04", "16:30", "customer_request")
        # started, still being filled in
        b = make("DEMO-8", "Farhan Ali", "pune", "tata_nexon", "2026-11-23", at="11:00")
        services.assign(ops, b, e1.id)
        start(b, e1)
        self._pending_asset(b, e1, "selfie", "uploading", 2)             # a stuck upload
        b = make("DEMO-9", "Sneha Kulkarni", "delhi", "hyundai_creta", "2026-11-23", "ev", "12:00")
        services.assign(ops, b, e2.id)
        start(b, e2, "ev")
        # submitted, photos never arrived, and its report failed
        b = make("DEMO-10", "Imran Qureshi", "mumbai", "maruti_victoris", "2026-11-22")
        services.assign(ops, b, e1.id)
        start(b, e1)
        late = self._pending_asset(b, e1, "selfie", "pending", 3)
        submissions.submit(e1, b, uuid.uuid4(), {
            "inspection": self._pdi_answers(b, e1, "MA3IMRANQ0000010", 31800,
                                            door_driver_front="minor_scratches",
                                            expert_comments="Small scratch on the door."),
            "start": {"selfie": [late]}, "end": {"taking_payment": False}})
        from apps.reports.models import Report

        Report.objects.update_or_create(booking=b, defaults={
            "status": "failed", "error": "A photo could not be read, so the PDF was not made."})
        # completed
        for ref, name, city, car, day, expert, chassis, km in (
                ("DEMO-11", "Deepa Menon", "pune", "tata_nexon", "2026-11-21", e1,
                 "MA3DEEPAM0000011", 12400),
                ("DEMO-12", "Karan Malhotra", "mumbai", "maruti_victoris", "2026-11-20", e2,
                 "MA3KARANM0000012", 56200)):
            b = make(ref, name, city, car, day)
            services.assign(ops, b, expert.id)
            start(b, expert)
            submit(b, expert, chassis, km)
            check_completion(b.id)
        # completed Used car and EV inspections, so every type has a finished one with a PDF
        for ref, name, city, car, itype, km in (
                ("DEMO-16", "Sanjay Verma", "delhi", "hyundai_creta", "used_car", 48200),
                ("DEMO-17", "Tanvi Shah", "mumbai", "tata_nexon", "ev", 14500)):
            b = make(ref, name, city, car, "2026-11-19", itype)
            services.assign(ops, b, e1.id)
            start(b, e1, itype)
            selfie = self._selfie(b, e1)
            submissions.submit(e1, b, uuid.uuid4(), {
                "inspection": self._form_answers(b, e1, itype, km),
                "start": {"selfie": [selfie]}, "end": {"taking_payment": False}})
            check_completion(b.id)
        # cancelled
        b = make("DEMO-13", "Lata Joshi", "delhi", "hyundai_creta", "2026-11-25")
        services.assign(ops, b, e2.id)
        services.cancel(ops, b, "customer_cancelled")
        # two experts inspected it: a conflict for Ops to resolve
        b = make("DEMO-14", "Manoj Pillai", "delhi", "tata_nexon", "2026-11-23", at="15:00")
        services.assign(ops, b, e1.id)
        start(b, e1)
        services.force_release(ops, b)
        services.assign(ops, b, e2.id)
        start(b, e2)
        submit(b, e2, "MA3MANOJP0000014", 22000, expert_comments="Second expert.")
        submit(b, e1, "MA3MANOJP0000014", 22010, expert_comments="First expert, offline.")
        # Ops changed the type while the expert had already started another one
        b = make("DEMO-15", "Neha Bhat", "pune", "maruti_victoris", "2026-11-23", at="17:00")
        services.assign(ops, b, e1.id)
        services.change_type(ops, b, "used_car")
        submissions.start(e1, b, uuid.uuid4(), None, "pdi", None,
                          {"selfie": [self._selfie(b, e1)]})

    # ---------------------------------------------------------------- today's schedule

    # (expert number or None, type, booked hour from now, state, minutes late, minutes taken)
    # two finish too quickly for the default limits (EV 25 < 40, Used car 30 < 45)
    TODAY: list[tuple[Any, ...]] = [
        (3, "used_car", -6, "done", 0, 55), (3, "ev", -4.5, "done", 25, 70),
        (3, "pdi", 1.5, "planned"),
        (4, "used_car", -5, "done", 0, 80), (4, "pdi", -1.2, "running", 0),
        (5, "ev", -3, "done", 40, 90), (5, "used_car", 2, "planned"),
        (6, "pdi", -0.5, "running", 20),
        (7, "used_car", -7, "done", 5, 60), (7, "ev", -5.5, "done", 0, 25),
        (8, "pdi", -0.8, "running", 0), (8, "used_car", -0.3, "planned"),
        (9, "ev", 1, "planned"), (9, "pdi", 3, "planned"),
        (10, "used_car", -2, "done", 10, 100), (10, "ev", 0.2, "planned"),
        (11, "pdi", -2, "running", 10),
        (12, "ev", -8, "done", 0, 50), (12, "used_car", -6, "done", 0, 30),
        (12, "ev", -4, "done", 15, 70),
        (13, "pdi", 4, "planned"), (14, "ev", -1, "running", 35),
        (None, "pdi", 0.5, "planned"), (None, "used_car", -1, "planned"),
        (None, "ev", 3, "planned")]

    def _today(self):
        """About 25 bookings for today, placed from the clock now: some finished (with the time
        they really took), some running (some started late), some still to come, some unassigned,
        and a few experts left with nothing, so the Today schedule has every case to look at."""
        from datetime import datetime, time

        from apps.bookings.models import Inspection

        ops = User.objects.get(username="ops")
        experts = {n: User.objects.get(username=f"expert{n}") for n in range(3, 15)}
        now = timezone.localtime()
        h = now.hour + now.minute / 60
        midnight = datetime.combine(now.date(), time(0), tzinfo=now.tzinfo)

        def at(x):         # an hour of today, kept inside the day
            return midnight + timedelta(hours=min(23.9, max(0, x)))

        def hhmm(x):
            m = max(0, min(23 * 60 + 30, round(x * 12) * 5))
            return f"{m // 60:02d}:{m % 60:02d}"

        names = ["Aarav Kapoor", "Bhavna Rao", "Chetan Pawar", "Disha Malik", "Eshan Arora",
                 "Fatima Syed", "Girish Nair", "Hema Pillai", "Irfan Mirza", "Jaya Kamat",
                 "Kabir Sethi", "Leena Dsouza", "Mohan Rathi", "Nisha Gill", "Omkar Jadhav",
                 "Preeti Saini", "Qasim Ali", "Radhika Iyer", "Sameer Dutta", "Trisha Bhat",
                 "Uday Shetty", "Vandana Roy", "Waqar Hussain", "Yash Thakur", "Zoya Merchant"]
        cities = ["delhi", "pune", "mumbai"]
        cars = ["maruti_victoris", "tata_nexon", "hyundai_creta", "mahindra_xuv_3xo"]
        for n, (num, itype, off, state, *rest) in enumerate(self.TODAY):
            ref = f"DEMO-{18 + n}"
            city = cities[n % 3]
            b = services.create(ops, {
                "booking_id": ref, "customer_name": names[n], "customer_phone": f"98765020{n:02d}",
                "address": f"{ref} road, {city.title()}", "city": city,
                "car_make_model": cars[n % 4], "inspection_type": itype,
                "inspection_date": now.date().isoformat(), "inspection_time": hhmm(h + off)})
            if num is None:
                continue
            expert = experts[num]
            services.assign(ops, b, expert.id)
            if state == "planned":
                continue
            selfie = self._selfie(b, expert)
            submissions.start(expert, b, uuid.uuid4(), None, itype, None, {"selfie": [selfie]})
            b.refresh_from_db()
            began = h + off + rest[0] / 60
            if state == "done":
                submissions.submit(expert, b, uuid.uuid4(), {
                    "inspection": self._form_answers(b, expert, itype, 30000 + n * 1000),
                    "start": {"selfie": [selfie]}, "end": {"taking_payment": False}})
                check_completion(b.id)
                Inspection.objects.filter(booking=b, status="submitted").update(
                    submitted_at=at(began + rest[1] / 60))
            b.refresh_from_db()
            b.started_at = at(began)                                     # when it really began
            timing.stamp_late(b)
            if state == "done":
                timing.stamp_duration(b, at(began + rest[1] / 60))
            b.save(update_fields=["started_at", "late_minutes", "duration_minutes"])

    # ---------------------------------------------------------------- integrations

    def _integrations(self, admin):
        """Webhooks with a mix of delivered, retrying and failed attempts, and two API keys."""
        from apps.integrations import apikeys
        from apps.integrations.models import ApiKey, Delivery, Integration

        forms = {f.key: f for f in Form.objects.filter(type__in=["booking", "custom"])}
        host = "http://127.0.0.1:9099"
        token = [{"key": "Authorization", "value": "Bearer demo-token"}]
        # name -> (form, event, extra columns); one integration is one event
        specs: dict[str, tuple[Form, str, dict[str, Any]]] = {
            "ERP: new bookings": (forms["booking"], "booking.created", {"url": f"{host}/erp",
                                  "headers": token}),
            "ERP: booking changes": (forms["booking"], "booking.updated", {
                "method": "PUT", "url": host + "/erp/{{job.booking_id}}",
                "query": [{"key": "src", "value": "vayu"}], "headers": token,
                "body_mode": "custom", "body": {
                    "ref": "{{job.booking_id}}",
                    "customer": {"name": "{{booking.customer_name}}", "city": "{{booking.city}}"},
                    "changed": "{{event.changed_fields}}"}}),
            "WhatsApp: inspection done": (forms["pdi"], "inspection.submitted",
                                          {"url": f"{host}/whatsapp"}),
            "WhatsApp: PDF ready": (forms["pdi"], "pdf.ready", {
                "url": f"{host}/whatsapp", "body_mode": "custom", "body": {
                    "ref": "{{job.booking_id}}", "chassis": "{{inspection.chassis_no}}",
                    "overall": "{{result.overall}}", "report": "{{link.pdf}}"}}),
            "Alerts: conflict": (forms["pdi"], "alert.conflict", {"url": f"{host}/alerts"}),
            "Alerts: stuck upload": (forms["pdi"], "alert.stuck_upload", {"url": f"{host}/alerts"}),
            "Old CRM (switched off)": (forms["booking"], "booking.created",
                                       {"url": f"{host}/old", "is_active": False}),
        }
        made = {name: Integration.objects.create(
            form=form, name=name, event=event, include_data=True,
            include_pdf=event == "pdf.ready", created_by=admin, **extra)
            for name, (form, event, extra) in specs.items()}
        refs = {b.booking_id: b for b in Booking.objects.all()}
        now = timezone.now()

        def delivery(integration, ref, status, attempts, **kw):
            b = refs.get(ref)
            return Delivery.objects.create(
                integration=made[integration], event=made[integration].event, booking=b,
                booking_uuid=str(b.id) if b else "", booking_ref=ref, status=status,
                attempts=attempts, last_attempt_at=now - timedelta(minutes=kw.pop("ago", 30)),
                **kw)

        ok = {"response_status": 200}
        delivery("ERP: new bookings", "DEMO-11", "success", 1, ago=600, **ok)
        delivery("ERP: new bookings", "DEMO-12", "success", 2, ago=380, **ok)
        delivery("ERP: new bookings", "DEMO-14", "retrying", 2, response_status=503,
                 error="http_503", next_retry_at=now + timedelta(hours=1), ago=25)
        delivery("ERP: booking changes", "DEMO-11", "success", 1, ago=420, **ok)
        delivery("ERP: booking changes", "DEMO-9", "failed", 7, response_status=500,
                 error="retries_exhausted", ago=300)
        delivery("WhatsApp: inspection done", "DEMO-11", "success", 1, response_status=204,
                 ago=410)
        delivery("WhatsApp: inspection done", "DEMO-12", "failed", 1, response_status=404,
                 error="http_404", ago=370)
        delivery("WhatsApp: PDF ready", "DEMO-11", "success", 1, response_status=204, ago=405)
        delivery("WhatsApp: PDF ready", "DEMO-3", "failed", 1, error="request_failed", ago=900)
        delivery("Alerts: conflict", "DEMO-14", "success", 1, response_status=200, ago=20)
        delivery("Alerts: conflict", "DEMO-15", "failed", 1, error="blocked_address", ago=60)
        delivery("Alerts: stuck upload", "DEMO-10", "retrying", 3, error="connection_error",
                 next_retry_at=now + timedelta(minutes=30), ago=15)

        shown, prefix, hashed = apikeys.generate()
        ApiKey.objects.create(
            name="ERP read access", prefix=prefix, key_hash=hashed, created_by=admin,
            scope={"forms": {"booking": ["*"], "pdi": ["chassis_no", "odometer"]}},
            last_used_at=now - timedelta(hours=2))
        _, old_prefix, old_hash = apikeys.generate()
        ApiKey.objects.create(
            name="Old partner key (revoked)", prefix=old_prefix, key_hash=old_hash,
            created_by=admin, scope={"forms": {"booking": ["booking_id", "stage"]}},
            revoked_at=now - timedelta(days=9))
        self.stdout.write(f"A demo API key to try (shown only now): {shown}")
