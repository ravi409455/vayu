"""Local review only: three users, the booking / check-in / PDI forms and a PDF template, and a
few bookings in different states, so every screen has something to look at.

The inspection forms (PDI, Used car, EV...) are meant to be built by hand in the form builder;
the PDI form here is a small stand-in so the flow can be tried straight away."""
import uuid

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

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
                            ("hyundai_creta", "Hyundai Creta")]}
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
        admin = User.objects.get(username="admin")
        booking = form_services.create_form(admin, key="booking", kind="booking", name="Booking")
        _publish(booking)
        self._ops_form(admin)
        self._inspection_forms(admin)
        self._bookings()
        self.stdout.write(self.style.SUCCESS(
            f"Demo ready. Sign in as admin / ops / expert / expert2 with password {PASSWORD}"))

    def _ops_form(self, admin):
        """The check-in/wrap-up system form comes with its locked fields; add a few custom ones
        and a payment QR picture beside them."""
        import io

        from PIL import Image

        from apps.forms import assets

        form = form_services.create_form(admin, key="checkin", kind="ops",
                                         name="Check-in and wrap-up")
        v = form.versions.get(status="draft")
        pay = Section.objects.get(version=v, title="Payment")
        paid = {"==": [{"var": "ops.taking_payment"}, True]}
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
        wrap = Page.objects.get(version=v, slot="after")
        review = Section.objects.create(version=v, page=wrap, title="Review", order=1)
        _field(v, review, "google_review", "Google review taken", "yes_no")
        shot = {"==": [{"var": "ops.google_review"}, True]}
        _field(v, review, "review_screenshot", "Review screenshot", "photo", show_if=shot,
               config={"max_count": 1})
        _field(v, review, "perfume_given", "Car perfume given", "yes_no")
        _publish(form)

    def _inspection_forms(self, admin):
        from apps.core import demo_forms as d
        from apps.reports import service as reports

        d.library_items(admin)
        for key, name, itype, pages, code, title in (
                ("pdi", "PDI", "pdi", d.pdi_pages(), "PDI",
                 "PRE DELIVERY CAR INSPECTION REPORT"),
                ("used_car", "Used car", "used_car", d.used_pages(), "UC",
                 "USED CAR INSPECTION REPORT"),
                ("ev", "EV", "ev", d.ev_pages(), "EV", "ELECTRIC CAR INSPECTION REPORT")):
            form, keys = d.build_inspection(admin, key=key, name=name, itype=itype, pages=pages)
            template = reports.create_template(admin, form)
            draft = template.versions.get(status="draft")
            definition = d.pdf_definition(code, title, keys, pages)
            saved = reports.save_definition(admin, draft, definition, draft.row_version)
            reports.publish(admin, saved, saved.row_version)

    def _selfie(self, booking, expert) -> str:
        """A real (tiny) verified picture, so the completed demo booking has its selfie."""
        import hashlib
        import io

        from PIL import Image

        from apps.media import storage
        from apps.media.models import MediaAsset

        buf = io.BytesIO()
        Image.new("RGB", (120, 90), (166, 40, 48)).save(buf, "JPEG")
        data = buf.getvalue()
        a = MediaAsset(client_uuid=uuid.uuid4(), booking=booking, uploaded_by=expert,
                       field_key="selfie", kind="photo", content_type="image/jpeg",
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
        b3 = make("DEMO-3", "Sunita Iyer (completed, has a PDF)", "delhi", "hyundai_creta",
                  "2026-11-24")
        services.assign(ops, b3, expert.id)
        _, _ = submissions.start(expert, b3, uuid.uuid4(), None, "pdi", None)
        b3.refresh_from_db()
        selfie = self._selfie(b3, expert)
        submissions.submit(expert, b3, uuid.uuid4(), {
            "inspection": {"chassis_no": "MA3YPKCSKTJ273129", "registration_no": "DL1CAB1234",
                           "odometer": 4200, "bonnet": "ok", "door_fl": "minor",
                           "remarks": "Clean car."},
            "ops": {"taking_payment": False, "selfie": [selfie]}})
        check_completion(b3.id)        # Completed: the PDF is made by the worker
