"""Load-test server side (docs/plan-load-test.md): loadtest_prepare (real form and --test-form)
and loadtest_cleanup. Test servers only; the clean-up deletes the load test's files and nothing
else in the bucket."""
import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.models import Role, User
from apps.bookings.models import Booking
from apps.integrations.models import ApiKey, Integration
from apps.media import storage
from apps.media.tests.conftest import s3  # noqa: F401  (in-memory storage)

pytestmark = pytest.mark.django_db(transaction=True, serialized_rollback=True)
PW = "Loadtest-pass-123"
SMALL = {"receiver": "https://receiver.example.com", "experts": 3, "ops": 1, "history_days": 1,
         "per_day": 4, "inspected_per_day": 2, "today": 2}


def _setup(settings):
    settings.SERVER_KIND, settings.SERVER_NAME = "test", "lt-small"
    User.objects.create_user(username="admin", password=PW, role=Role.ADMIN, name="Admin")
    call_command("setup_platform", verbosity=0)


def _files(tpl: dict) -> dict[str, int]:
    """How many photos and videos a template's inspection sends."""
    out = {"photo": 0, "video": 0}
    for field, n in tpl["files"].items():
        kind = "video" if any(str(x).startswith("@video") for x in tpl["answers"].get(field, []))\
            else "photo"
        out[kind] += n
    return out


def test_refused_on_production(settings, s3, tmp_path):  # noqa: F811
    settings.SERVER_KIND = "production"
    with pytest.raises(CommandError, match="production"):
        call_command("loadtest_prepare", password=PW, out=str(tmp_path / "lt.json"), **SMALL)
    with pytest.raises(CommandError, match="production"):
        call_command("loadtest_cleanup")


def test_test_form_prepare_and_cleanup(settings, s3, tmp_path, capsys):  # noqa: F811
    _setup(settings)
    storage.put("bookings/staging-own/file.jpg", b"x", "image/jpeg")        # staging's own file
    out = tmp_path / "lt.json"
    call_command("loadtest_prepare", password=PW, out=str(out), test_form=True, **SMALL)
    data = json.loads(out.read_text())
    assert oct(out.stat().st_mode)[-3:] == "600"                             # logins and a key
    assert data["inspection_type"] == "loadtest"
    assert _files(data["templates"]["inspection"]) == {"photo": 100, "video": 15}   # the owner's
    assert _files(data["templates"]["inspection_big"]) == {"photo": 150, "video": 15}
    assert len(data["experts"]) == 3 and len(data["today"]) == 2
    key = ApiKey.objects.get(name="load test", revoked_at=None)
    assert set(key.scope["forms"]) == {"booking", "loadtest"}   # reads the test form's inspections
    hooks = Integration.objects.filter(name__startswith="load test")
    assert hooks.filter(event="booking.created", form__key="booking").count() == 10
    assert hooks.filter(event="inspection.submitted", form__key="loadtest").count() == 10
    assert Booking.objects.filter(booking_id__startswith="LT-H").count() == 4     # the history

    # again (each capacity step): no second history, the webhooks still exactly 10 + 10
    call_command("loadtest_prepare", password=PW + "2", out=str(out), test_form=True, **SMALL)
    assert Booking.objects.filter(booking_id__startswith="LT-H").count() == 4
    assert Integration.objects.filter(name__startswith="load test").count() == 20
    assert ApiKey.objects.filter(name="load test", revoked_at=None).count() == 1

    capsys.readouterr()
    call_command("loadtest_cleanup")
    result = json.loads(capsys.readouterr().out)
    assert result["files_deleted"] > 0 and result["left_in_their_folders"] == 0
    left = {o["Key"] for o in storage.client().list_objects_v2(
        Bucket=settings.S3_BUCKET).get("Contents", [])}
    assert "bookings/staging-own/file.jpg" in left                           # untouched


def test_real_form_sends_five_videos(settings, s3, tmp_path):  # noqa: F811
    _setup(settings)
    out = tmp_path / "lt.json"
    call_command("loadtest_prepare", password=PW, out=str(out), **SMALL)
    data = json.loads(out.read_text())
    assert data["inspection_type"] == "pdi"
    assert _files(data["templates"]["inspection"]) == {"photo": 100, "video": 5}
