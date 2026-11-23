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
from apps.bookings import services, submissions
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
         ("newuser", Role.OPS, "Nina New (must change password)", True)]
LISTS = {"city": [("delhi", "Delhi"), ("pune", "Pune"), ("mumbai", "Mumbai")],
         "car_make_model": [("maruti_victoris", "Maruti Victoris"), ("tata_nexon", "Tata Nexon"),
                            ("hyundai_creta", "Hyundai Creta"),
                            ("mahindra_xuv_3xo", "Mahindra XUV 3XO AX5")]}
DEFECT = {"options": [{"key": "ok", "label": "OK"},
                      {"key": "dent", "label": "Dent", "is_defect": True, "severity": "minor"},
                      {"key": "crack", "label": "Crack", "is_defect": True, "severity": "major"}]}


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

    def handle(self, *args, if_empty=False, **options):
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
        from apps.core import demo_forms as d
        from apps.core import demo_pdi
        from apps.reports import service as reports

        d.library_items(admin)
        form, _ = demo_pdi.build_pdi(admin)
        template = reports.create_template(admin, form)
        draft = template.versions.get(status="draft")
        logo, mark = self._brand_assets(admin)
        disclaimer = (Path(demo_pdi.__file__).parent / "seed_assets" / "pdi-disclaimer.html")
        definition = demo_pdi.pdf_definition(str(logo.id), str(mark.id),
                                             disclaimer.read_text())
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
            out.append(assets.create_asset(admin, buf.getvalue()))
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

        make("DEMO-1", "Kavya Rao (not assigned)", "delhi", "maruti_victoris", "2026-12-01")
        b2 = make("DEMO-2", "Arjun Mehta (assigned to Ravi)", "pune", "tata_nexon", "2026-12-01")
        services.assign(ops, b2, expert.id)
        b3 = make("DEMO-3", "Sunita Iyer (completed, has a PDF)", "delhi", "mahindra_xuv_3xo",
                  "2026-11-24")
        services.assign(ops, b3, expert.id)
        selfie = self._selfie(b3, expert)          # the check-in selfie: the job starts with it
        submissions.start(expert, b3, uuid.uuid4(), None, "pdi", None, {"selfie": [selfie]})
        b3.refresh_from_db()
        submissions.submit(expert, b3, uuid.uuid4(), {   # the sample report AV66022, in full
            "inspection": self._pdi_answers(b3, expert, "MA1NS2NP1T2H75335", 39),
            "start": {"selfie": [selfie]}, "end": {"taking_payment": False}})
        check_completion(b3.id)        # Completed: the PDF is made by the worker


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
        from apps.core.demo_pdi import sample_answers

        version = Form.objects.get(key="pdi").versions.get(status="published")
        answers, photos = sample_answers(version, chassis, odometer=odometer, **overrides)
        labels = dict(Field.objects.filter(version=version).values_list("key", "label"))
        for key in photos:
            answers[key] = [self._photo(booking, expert, key, labels[key])]
        return answers

    def _more_bookings(self):
        """Bookings in every stage, plus the situations that fill the Problems page."""
        ops = User.objects.get(username="ops")
        e1, e2 = User.objects.get(username="expert"), User.objects.get(username="expert2")
        base = {"inspection_time": "10:30"}
        phones = iter(["9876501001", "9876501002", "9876501003", "9876501004", "9876501005",
                       "9876501006", "9876501007", "9876501008", "9876501009", "9876501010",
                       "9876501011", "9876501012", "9876501013"])

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

    # ---------------------------------------------------------------- integrations

    def _integrations(self, admin):
        """Webhooks with a mix of delivered, retrying and failed attempts, and two API keys."""
        from apps.bookings.models import Booking
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
