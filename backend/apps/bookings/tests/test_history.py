"""F-247: the history metrics need outlives what it describes."""
import pytest

from apps.bookings.models import BookingActivity
from apps.bookings.tests.test_submissions import assign, ienv, start  # noqa: F401
from apps.media.tests.conftest import s3  # noqa: F401

pytestmark = pytest.mark.django_db


def test_a_deleted_bookings_timeline_is_kept_with_its_booking_id(ienv, booking):
    assign(ienv, booking)
    start(ienv.expert, booking)
    rows = BookingActivity.objects.filter(booking_id=booking["id"]).count()
    assert rows and ienv.admin.delete(f"/api/v1/bookings/{booking['id']}").status_code == 204
    kept = BookingActivity.objects.filter(booking_ref="SA37926")
    assert kept.count() == rows and not kept.exclude(booking=None).exists()


def test_the_migration_names_old_rows(ienv, booking):
    from importlib import import_module

    from django.apps import apps as django_apps

    BookingActivity.objects.update(booking_ref="")
    import_module("apps.bookings.migrations.0014_f247_history").fill_refs(django_apps, None)
    assert set(BookingActivity.objects.values_list("booking_ref", flat=True)) == {"SA37926"}
