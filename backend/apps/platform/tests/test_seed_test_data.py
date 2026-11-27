"""Test data for outside testers: guarded wipe, then every flow filled in."""
import uuid

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
    # a rule that looks at the booking counts here too: a Used Car's body frame photo is required
    from apps.media.models import MediaAsset

    used = next(b for b in Booking.objects.filter(stage="submitted", inspection_type="used_car"))
    counted = used.counted_inspection()
    assert counted is not None
    frame = counted.answers["inspection"]["driver_side_a_pillar_image"]
    MediaAsset.objects.filter(id__in=frame).update(status="uploading")
    row = next(r for r in missing_files(used) if r["key"] == "driver_side_a_pillar_image")
    assert row["required"] is True
    # Ops' own key checks print in a table of their own, only on a report that has some
    import io

    import pypdf

    from apps.reports.tasks import build_pdf, published_template

    def report_text(ref: str) -> str:
        b = Booking.objects.get(booking_id=ref)
        insp = b.counted_inspection()
        assert insp is not None
        template = published_template(b, insp)
        assert template is not None
        pdf, _ = build_pdf(b, insp, template, "tok", 1)
        return "\n".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(pdf)).pages)

    named = report_text("TST-1001")
    assert "Additional key checks" in named and "Service history" in named
    assert "Verified, 3 services" in named and "Clean car overall" in named
    assert "Key Check 3" not in named                       # an unnamed pair prints nothing
    for text in (named, used_report := report_text("TST-1002")):   # a late start is not printed
        assert "Inspection Delay" not in text and "45 Minutes Delayed" not in text
    # TST-1001..1003 took a late-start payment and a wrap-up payment by UPI: the screenshots are
    # on the booking, hidden from the customer (not in the report's photos or its download)
    from apps.media.models import MediaAsset
    from apps.reports import context as report_context
    from apps.reports import media_links

    for ref in ("TST-1001", "TST-1002", "TST-1003"):
        paid = Booking.objects.get(booking_id=ref)
        made = paid.counted_inspection()
        assert made is not None
        assert made.answers["inspection"]["delay_payment_screenshot"]
        assert made.answers["end"]["payment_screenshot"]
        shots = set(MediaAsset.objects.filter(booking=paid, field_key__contains="payment")
                    .values_list("id", flat=True))
        assert len(shots) == 2
        src = report_context.Source(paid, made, revision=1, token="t")
        assert not shots & {uuid.UUID(i) for i in media_links.named(src, "photos")}
    plain = report_text("TST-1009")
    assert "Additional key checks" not in plain and "Key Check 1" not in plain
    assert "Mfg. Date" in named and "March 2026" in named            # on the cover (PDI, EV)
    assert "Estimated Price" in used_report and "12,50,000" in used_report
    assert "Service history" in used_report and "36,400 km" in used_report
    assert "Not able to check" in used_report           # an empty answer prints its fallback
    assert "Mfg. Date" not in used_report and "Estimated Price" not in named
    # the cover counts everything the expert recorded; "Not able to check" has no tile or list
    for text in (named, plain, used_report):
        cover = text.upper().split("DOCUMENTS")[0]            # the table headings print in capitals
        assert "CHECKPOINTS INSPECTED" in cover and "CHECKS DONE" not in cover
        assert "NOT ABLE TO CHECK" not in cover and "Not able to check:" not in text
    # the count is the form's predefined checkpoints: the same on every inspection of a type
    from apps.reports import context

    counts: dict[str, set[str]] = {}
    for done in Booking.objects.filter(stage="completed"):
        made = done.counted_inspection()
        assert made is not None
        src = context.Source(done, made, revision=1, token="t")
        counts.setdefault(done.inspection_type, set()).add(src.values()["sys"]["points"])
    assert counts == {"pdi": {"335"}, "used_car": {"349"}, "ev": {"302"}}, counts
    # the expert's own summary text is never printed (as in Clappia): only Ops' comment is
    assert "Expert comments" in named and "Minor issues noted" not in named
    assert "Expert comments" not in plain and "Minor issues noted" not in plain
    assert "Photos of Issues" in named or "Photos of Issues" in plain       # its photos still are
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
