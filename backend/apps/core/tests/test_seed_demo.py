import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.models import User
from apps.bookings.models import Booking
from apps.media.tests.conftest import s3  # noqa: F401  (in-memory S3 for the PDF)
from apps.reports.models import Report

pytestmark = pytest.mark.django_db


def test_the_demo_seed_builds_users_forms_and_bookings_in_every_state():
    call_command("seed_demo")
    assert set(User.objects.values_list("username", flat=True)) >= {"admin", "ops", "expert",
                                                                    "expert2", "newuser"}
    assert User.objects.get(username="newuser").must_change_password is True
    stages = dict(Booking.objects.values_list("booking_id", "stage"))
    assert stages == {
        "DEMO-1": "draft", "DEMO-2": "assigned", "DEMO-3": "completed", "DEMO-4": "draft",
        "DEMO-5": "draft", "DEMO-6": "assigned", "DEMO-7": "assigned", "DEMO-8": "in_progress",
        "DEMO-9": "in_progress", "DEMO-10": "submitted", "DEMO-11": "completed",
        "DEMO-12": "completed", "DEMO-13": "cancelled", "DEMO-14": "completed",
        "DEMO-15": "in_progress"}
    assert Report.objects.get(booking__booking_id="DEMO-3").status == "ready"
    with pytest.raises(CommandError, match="already exists"):
        call_command("seed_demo")


def test_the_demo_seed_fills_the_problems_page_and_the_integrations_screens():
    from apps.integrations.models import ApiKey, Delivery, Integration
    from apps.media.services import stuck_uploads

    call_command("seed_demo")
    assert {a.booking.booking_id for a in stuck_uploads()} == {"DEMO-8", "DEMO-10"}
    assert Booking.objects.get(booking_id="DEMO-14").conflict == "TWO_EXPERTS"
    assert any(a["code"] == "TYPE_CHANGE_REJECTED"
               for a in Booking.objects.get(booking_id="DEMO-15").alerts)
    assert Report.objects.get(booking__booking_id="DEMO-10").status == "failed"
    assert Integration.objects.count() == 4 and Integration.objects.filter(is_active=False).count() == 1
    assert {d.status for d in Delivery.objects.all()} >= {"success", "retrying", "failed"}
    assert ApiKey.objects.count() == 2 and ApiKey.objects.filter(revoked_at__isnull=False).count() == 1


def test_the_demo_seed_refuses_to_run_with_other_settings(settings):
    settings.SETTINGS_MODULE = "vayu.settings.prod"
    with pytest.raises(CommandError, match="only runs with"):
        call_command("seed_demo")


def test_the_demo_seed_can_be_told_to_leave_existing_data_alone():
    call_command("seed_demo")
    call_command("seed_demo", "--if-empty")                  # no error, nothing duplicated
    assert User.objects.filter(username="admin").count() == 1


def test_the_demo_forms_are_large_and_the_library_is_not_empty():
    from apps.forms.models import Field, Form, LibraryItem, Page, Section

    call_command("seed_demo")
    for key, minimum in (("pdi", 150), ("used_car", 150), ("ev", 120)):
        form = Form.objects.get(key=key)
        v = form.versions.get(status="published")
        assert Field.objects.filter(version=v).count() >= minimum
        assert Page.objects.filter(version=v).count() >= 8
        assert Section.objects.filter(version=v).count() >= 10
        assert v.rating_config["categories"]
    assert LibraryItem.objects.count() >= 7
    assert Page.objects.filter(version__form__key="pdi", gate=True).exists()
    assert Section.objects.filter(version__form__key="pdi", library_item__isnull=False).exists()
