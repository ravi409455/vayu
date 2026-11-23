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
    assert stages == {"DEMO-1": "draft", "DEMO-2": "assigned", "DEMO-3": "completed"}
    assert Report.objects.get(booking__booking_id="DEMO-3").status == "ready"
    with pytest.raises(CommandError, match="already exists"):
        call_command("seed_demo")


def test_the_demo_seed_refuses_to_run_with_other_settings(settings):
    settings.SETTINGS_MODULE = "vayu.settings.prod"
    with pytest.raises(CommandError, match="only runs with"):
        call_command("seed_demo")


def test_the_demo_seed_can_be_told_to_leave_existing_data_alone():
    call_command("seed_demo")
    call_command("seed_demo", "--if-empty")                  # no error, nothing duplicated
    assert User.objects.filter(username="admin").count() == 1
