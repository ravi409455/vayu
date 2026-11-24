import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.models import User
from apps.bookings.models import Booking
from apps.media.tests.conftest import s3  # noqa: F401  (in-memory S3 for the PDF)
from apps.reports.models import Report

pytestmark = pytest.mark.django_db


def test_the_demo_seed_builds_users_forms_and_bookings_in_every_state():
    call_command("seed_demo", "--no-today")
    assert set(User.objects.values_list("username", flat=True)) >= {"admin", "ops", "expert",
                                                                    "expert2", "newuser"}
    assert User.objects.get(username="newuser").must_change_password is True
    stages = dict(Booking.objects.values_list("booking_id", "stage"))
    assert {k: v for k, v in stages.items() if int(k[5:]) <= 17} == {
        "DEMO-1": "draft", "DEMO-2": "assigned", "DEMO-3": "completed", "DEMO-4": "draft",
        "DEMO-5": "draft", "DEMO-6": "assigned", "DEMO-7": "assigned", "DEMO-8": "in_progress",
        "DEMO-9": "in_progress", "DEMO-10": "submitted", "DEMO-11": "completed",
        "DEMO-12": "completed", "DEMO-13": "cancelled", "DEMO-14": "completed",
        "DEMO-15": "in_progress", "DEMO-16": "completed", "DEMO-17": "completed"}
    assert Report.objects.get(booking__booking_id="DEMO-3").status == "ready"
    for ref in ("DEMO-16", "DEMO-17"):                  # a finished Used car and EV, with their PDFs
        assert Report.objects.get(booking__booking_id=ref).status == "ready", ref
    assert Booking.objects.filter(stage="completed").values_list("inspection_type", flat=True) \
        .distinct().count() == 3
    with pytest.raises(CommandError, match="already exists"):
        call_command("seed_demo", "--no-today")


def test_the_demo_has_the_real_team_and_a_busy_day_for_the_today_schedule():
    from django.utils import timezone

    from apps.bookings.models import Inspection

    call_command("seed_demo")
    assert User.objects.filter(role="expert").count() == 20
    assert User.objects.filter(role="ops").count() == 3 and User.objects.filter(role="admin").count() == 1
    today = Booking.objects.filter(inspection_date=timezone.localdate(), booking_id__regex=r"^DEMO-(1[89]|[2-4]\d)$")
    assert today.count() == 25
    assert today.filter(assigned_expert__isnull=True).count() == 3
    busy = set(today.exclude(assigned_expert__isnull=True).values_list("assigned_expert", flat=True))
    assert len(busy) == 12                                   # expert3 to expert14; the rest are empty
    assert {b.stage for b in today} == {"draft", "assigned", "in_progress", "completed"}
    now = timezone.now()
    for b in today.filter(stage__in=["in_progress", "completed"]):
        assert b.started_at is not None and b.started_at <= now
    for i in Inspection.objects.filter(booking__in=today.filter(stage="completed"), status="submitted"):
        started, submitted = i.booking.started_at, i.submitted_at
        assert started is not None and submitted is not None
        assert started <= submitted <= now                         # it took real time, in the past


def test_the_demo_seed_fills_the_problems_page_and_the_integrations_screens():
    from apps.integrations.models import ApiKey, Delivery, Integration
    from apps.media.services import stuck_uploads

    call_command("seed_demo", "--no-today")
    assert {a.booking.booking_id for a in stuck_uploads()} == {"DEMO-8", "DEMO-10"}
    assert Booking.objects.get(booking_id="DEMO-14").conflict == "TWO_EXPERTS"
    assert any(a["code"] == "TYPE_CHANGE_REJECTED"
               for a in Booking.objects.get(booking_id="DEMO-15").alerts)
    assert Report.objects.get(booking__booking_id="DEMO-10").status == "failed"
    assert Integration.objects.count() == 7 and Integration.objects.filter(is_active=False).count() == 1
    assert {d.status for d in Delivery.objects.all()} >= {"success", "retrying", "failed"}
    assert ApiKey.objects.count() == 2 and ApiKey.objects.filter(revoked_at__isnull=False).count() == 1


def test_the_demo_seed_refuses_to_run_with_other_settings(settings):
    settings.SETTINGS_MODULE = "vayu.settings.prod"
    with pytest.raises(CommandError, match="only runs with"):
        call_command("seed_demo", "--no-today")


def test_the_demo_seed_can_be_told_to_leave_existing_data_alone():
    call_command("seed_demo", "--no-today")
    call_command("seed_demo", "--no-today", "--if-empty")                  # no error, nothing duplicated
    assert User.objects.filter(username="admin").count() == 1


def test_the_demo_forms_are_large_and_the_library_is_not_empty():
    from apps.forms.models import Field, Form, LibraryItem, Page, Section

    call_command("seed_demo", "--no-today")
    for key, minimum in (("pdi", 150), ("used_car", 150), ("ev", 120)):
        form = Form.objects.get(key=key)
        v = form.versions.get(status="published")
        assert Field.objects.filter(version=v).count() >= minimum
        assert Page.objects.filter(version=v).count() >= 8
        assert Section.objects.filter(version=v).count() >= 10
        assert v.rating_config["categories"]
    assert LibraryItem.objects.count() >= 7
    assert Page.objects.filter(version__form__key="pdi", gate=True).exists()
    assert Section.objects.filter(version__form__key="used_car", library_item__isnull=False).exists()


def test_the_pdi_form_is_the_full_one_from_the_sample_report():
    from apps.bookings.models import Booking
    from apps.forms.models import Field, Form, Section
    from apps.forms.rules import validate_version

    call_command("seed_demo", "--no-today")
    v = Form.objects.get(key="pdi").versions.get(status="published")
    assert validate_version(v) == []
    titles = list(Section.objects.filter(version=v).values_list("title", flat=True))
    assert {"Vehicle details", "CNG", "Documents", "Front", "Driver side", "Body frame", "Tyres",
            "Underbody", "Car pictures", "Summary"} <= set(titles)
    assert Section.objects.get(version=v, title="Glass and mirrors").key == "glass_and_mirrors"
    door = Field.objects.get(version=v, key="door_driver_front")
    tones = {o["key"]: o["tone"] for o in door.config["options"]}
    assert tones["ok"] == "ok" and tones["major_dents"] == "bad"
    photo = Field.objects.get(version=v, key="door_driver_front_photo")
    assert photo.config["photo_of"] == "door_driver_front" and photo.show_if
    assert Field.objects.get(version=v, key="issue_photos").config["issue_photo"] is True
    assert len(v.key_checks) == 9 and not Field.objects.filter(version=v, type="derived").exists()
    assert Field.objects.filter(version=v).count() >= 300
    # the sample booking is answered in full, with its pictures
    answers = Booking.objects.get(booking_id="DEMO-3").inspections.get().answers["inspection"]
    assert answers["window_driver_front"] == "loose" and answers["odometer"] == 39
    assert len(answers["picture_front"]) == 1 and "door_driver_front_photo" not in answers
    assert "cng_fitting" not in answers                            # petrol: no CNG section


def test_the_pdi_report_of_the_sample_booking_reads_like_the_sample():
    """The seeded PDI template rendered for DEMO-3 (the sample AV66022): no blank pages, every
    section title on the same page as its first row, page numbers, verify page, disclaimer."""
    import io

    import pypdf

    from apps.media import storage

    call_command("seed_demo", "--no-today")
    report = Report.objects.get(booking__booking_id="DEMO-3")
    assert report.status == "ready" and report.filename == "DEMO-3PDI.pdf"
    pages = [p.extract_text() for p in pypdf.PdfReader(io.BytesIO(storage.read(report.key))).pages]
    n = len(pages)
    assert 12 <= n <= 30
    assert all(len(t.strip()) > 20 for t in pages)                       # no blank pages
    numbered = [t for t in pages if f"of {n}" in t]
    assert len(numbered) == n - 1                                        # all but the divider
    for title, first_row in (("Front", "Front bonnet top"), ("Driver side", "Driver front fender"),
                             ("Tyres", "Driver front"), ("Warning lights", "Check engine light"),
                             ("Key checks", "Control panel lights"),
                             ("Issues found", "Driver front door window")):
        assert any(title in t and first_row in t for t in pages), title
    text = "\n".join(pages)
    for needle in ("PRE DELIVERY", "INSPECTION REPORT", "MA1NS2NP1T2H75335", "Deep Forest",
                   "Not Available", "Loose", "Detailed Report", "Verify this report",
                   "Arbitration and Conciliation Act, 1996", "+91-9429690830",
                   "The left front door glass outer weatherstrip is loose."):
        assert needle in text, needle
    assert "CNG hydro test" not in text                                 # petrol car: no CNG
