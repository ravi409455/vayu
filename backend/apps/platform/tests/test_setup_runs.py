"""The setup's runs on an empty platform: the first run publishes everything, later runs keep the
Admin's work, and the command adds staff. (What the built forms hold: test_setup_forms.py.)"""
import pytest

from apps.accounts.models import Role, User
from apps.media.tests.conftest import s3  # noqa: F401  (in-memory storage for the logo)
from apps.platform.tests.test_setup_forms import put_all

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin():
    return User.objects.create_user(username="setup_admin", password="x" * 12, role=Role.ADMIN)


def test_every_form_publishes_and_a_second_run_changes_nothing(admin):
    first = put_all(admin)
    assert all(r.startswith("published") for r in first.values()), first
    assert put_all(admin) == {k: "kept" for k in first}               # the Admin's now (H-11)
    assert put_all(admin, force=True) == {k: "unchanged" for k in first}


def test_the_setup_command_runs_twice_and_adds_staff_from_the_file(tmp_path, s3):  # noqa: F811
    from django.core.management import call_command

    staff = tmp_path / "staff.csv"
    staff.write_text("username,name,role,phone,password\nboss,Boss,admin,,\n"
                     "e1,Expert One,expert,9800000001,Secret-pass-1\n")
    from io import StringIO

    first = StringIO()
    call_command("setup_platform", users=str(staff), stdout=first)
    assert User.objects.get(username="e1").check_password("Secret-pass-1")
    assert User.objects.get(username="boss").must_change_password
    # F-233: the made-up password is in a file only the operator reads, never in the output
    made = (tmp_path / "staff.csv.passwords").read_text().split()
    assert made[0] == "boss" and User.objects.get(username="boss").check_password(made[1])
    assert made[1] not in first.getvalue()
    assert (tmp_path / "staff.csv.passwords").stat().st_mode & 0o777 == 0o600

    out = StringIO()
    call_command("setup_platform", users=str(staff), stdout=out)
    assert "published" not in out.getvalue() and "users added: 0" in out.getvalue()


def test_a_forced_setup_needs_the_server_name_and_keeps_the_admins_disclaimer(tmp_path, s3,  # noqa: F811
                                                                                settings):
    from django.core.management import call_command
    from django.core.management.base import CommandError

    from apps.reports import shared
    from apps.reports.models import SharedItem

    staff = tmp_path / "staff.csv"
    staff.write_text("username,name,role,phone,password\nboss,Boss,admin,,Boss-pass-123\n")
    call_command("setup_platform", users=str(staff))
    boss = User.objects.get(username="boss")
    item = SharedItem.objects.get(key="disclaimer")
    content = item.revisions.get(revision=item.revision).content
    edited = {"parts": [{**content["parts"][0], "html": "<p>ADMIN LEGAL</p>"}]}
    shared.save(boss, "snippet", "disclaimer", "Report disclaimer", edited)
    call_command("setup_platform")                                      # a plain re-run
    item.refresh_from_db()
    assert "ADMIN LEGAL" in str(item.revisions.get(revision=item.revision).content)
    settings.SERVER_NAME = "prod-1"
    with pytest.raises(CommandError, match="server's name"):
        call_command("setup_platform", force=True, confirm="wrong")
    call_command("setup_platform", force=True, confirm="prod-1")
    item.refresh_from_db()
    assert "ADMIN LEGAL" not in str(item.revisions.get(revision=item.revision).content)
