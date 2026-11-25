"""Test data for outside testers: guarded wipe, then every flow filled in."""
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.bookings.models import Booking
from apps.media.tests.conftest import s3  # noqa: F401  (in-memory storage)

pytestmark = pytest.mark.django_db(transaction=True, serialized_rollback=True)
PW = "Tester-pass-123"


def test_it_refuses_on_production_without_the_name_or_with_real_bookings(settings, s3):  # noqa: F811
    settings.SERVER_KIND = "production"
    with pytest.raises(CommandError, match="production"):
        call_command("seed_test_data", confirm="local", password=PW)
    settings.SERVER_KIND, settings.SERVER_NAME = "test", "staging-1"
    with pytest.raises(CommandError, match="name"):
        call_command("seed_test_data", confirm="wrong", password=PW)
    from apps.bookings.tests.conftest import create  # noqa: F401
    Booking.objects.create(booking_id="AV66022", answers={}, inspection_type="pdi")
    with pytest.raises(CommandError, match="real"):
        call_command("seed_test_data", confirm="staging-1", password=PW)
    assert Booking.objects.filter(booking_id="AV66022").exists()        # nothing wiped


def test_it_fills_every_flow(settings, s3):  # noqa: F811
    settings.SERVER_KIND, settings.SERVER_NAME = "test", "staging-1"
    call_command("seed_test_data", confirm="staging-1", password=PW)
    stages = {b.booking_id: b.stage for b in Booking.objects.all()}
    assert all(k.startswith("TST-") for k in stages)
    for stage in ("draft", "assigned", "in_progress", "completed", "cancelled"):
        assert stage in stages.values(), stage
    assert Booking.objects.exclude(conflict={}).exists() or Booking.objects.filter(
        conflict__isnull=False).exists()
    from apps.accounts.models import User

    assert User.objects.get(username="expert").check_password(PW)
    assert Booking.objects.filter(inspection_type="tour", assigned_expert__username="expert").exists()
    from apps.media.services import missing_files

    waiting = [missing_files(b) for b in Booking.objects.filter(stage="submitted")]
    assert any(rows and not any(r["required"] for r in rows) for rows in waiting)  # can finish
    assert any(any(r["required"] for r in rows) for rows in waiting)    # needs an upload first
    # a second run on the same (test-made) data is allowed and starts clean
    call_command("seed_test_data", confirm="staging-1", password=PW)


def test_a_local_settings_flag_never_wipes_a_production_database(settings, s3):  # noqa: F811
    """F-213: the database says what server it is (written by setup_platform), and bookings
    test data did not make stop the wipe on every kind of server."""
    from apps.core.models import Setting

    Setting.objects.create(key="server", value={"kind": "production", "name": "prod"})
    settings.SERVER_KIND, settings.SERVER_NAME = "local", "local"      # the wrong --settings
    with pytest.raises(CommandError, match="production"):
        call_command("seed_test_data", confirm="local", password=PW)
    Setting.objects.filter(key="server").delete()
    Booking.objects.create(booking_id="REAL-1", answers={}, inspection_type="pdi")
    with pytest.raises(CommandError, match="real"):
        call_command("seed_test_data", confirm="local", password=PW)    # local kind too
    assert Booking.objects.filter(booking_id="REAL-1").exists()


def test_e2e_reset_only_wipes_an_e2e_database(settings):
    settings.SETTINGS_MODULE = "vayu.settings.e2e"
    with pytest.raises(CommandError, match="e2e database"):
        call_command("e2e_reset")                    # the test database is no e2e one
