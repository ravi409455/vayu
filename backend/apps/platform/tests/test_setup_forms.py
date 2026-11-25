"""The setup's forms, each built from its own Clappia app read-out (apps/platform/setup/data)."""
import pytest

from apps.accounts.models import Role, User
from apps.forms.models import Field, Form
from apps.media.tests.conftest import s3  # noqa: F401  (in-memory storage for the logo)
from apps.platform.setup import build, forms, lists

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin():
    return User.objects.create_user(username="setup_admin", password="x" * 12, role=Role.ADMIN)


def put_all(admin, force=False) -> dict:
    lists.apply()
    out = {"booking": build.apply(admin, build.system_form("booking"), forms.booking(),
                                  force=force),
           "start": build.apply(admin, build.system_form("start"), forms.start(), force=force),
           "end": build.apply(admin, build.system_form("end"), forms.end(admin), force=force)}
    for key, name, itype, _ in forms.INSPECTIONS:
        spec, extra = forms.inspection(key)
        out[key] = build.apply(admin, build.ensure_form(admin, key=key, name=name, itype=itype),
                               spec, extra, force=force)
    return out


def live_fields(key):
    v = Form.objects.get(key=key).versions.filter(status="published").order_by("-number").first()
    return {f.key: f for f in Field.objects.filter(version=v)}


def test_every_form_publishes_and_a_second_run_changes_nothing(admin):
    first = put_all(admin)
    assert all(r.startswith("published") for r in first.values()), first
    assert put_all(admin) == {k: "kept" for k in first}               # the Admin's now (H-11)
    assert put_all(admin, force=True) == {k: "unchanged" for k in first}


def test_a_re_run_keeps_the_admins_edits_and_never_touches_their_draft(admin):
    from apps.bookings.tests.conftest import custom_form, publish_draft  # noqa: F401
    from apps.forms import services as form_services
    from apps.forms.models import FormVersion

    put_all(admin)
    form = Form.objects.get(key="pdi")
    live = form.versions.get(status="published")
    Field.objects.filter(version=live, key="chassis_no").update(label="ADMIN LABEL")
    draft = form_services.create_draft(admin, form)
    Field.objects.filter(version=draft, key="chassis_no").update(label="ADMIN DRAFT WORK")
    assert put_all(admin)["pdi"] == "kept"
    assert live_fields("pdi")["chassis_no"].label == "ADMIN LABEL"
    assert Field.objects.get(version=draft, key="chassis_no").label == "ADMIN DRAFT WORK"
    with pytest.raises(build.SetupRefused, match="draft open"):
        put_all(admin, force=True)
    assert FormVersion.objects.filter(pk=draft.pk, status="draft").exists()


def test_a_forced_run_publishes_a_new_version_with_clean_section_keys(admin):
    from apps.forms.models import Section

    put_all(admin)
    form = Form.objects.get(key="pdi")
    live = form.versions.get(status="published")
    Field.objects.filter(version=live, key="chassis_no").update(label="ADMIN LABEL")
    keys = set(Section.objects.filter(version=live).values_list("key", flat=True))
    assert put_all(admin, force=True)["pdi"].startswith("published v2")
    new = form.versions.filter(status="published").order_by("-number").first()
    assert set(Section.objects.filter(version=new).values_list("key", flat=True)) == keys
    assert live_fields("pdi")["chassis_no"].label != "ADMIN LABEL"
    assert form.versions.filter(pk=live.pk).exists()                  # never deleted


def test_each_inspection_keeps_its_own_apps_choices(admin):
    put_all(admin)
    pdi, used, ev = live_fields("pdi"), live_fields("used_car"), live_fields("ev")
    labels = lambda f: [o["label"] for o in f.config["options"]]  # noqa: E731
    # the same question, different answers per app (never copied across)
    assert "Expired" in labels(used["registration_certificate"])
    assert "Expired" not in labels(pdi["registration_certificate"])
    assert labels(used["multi_function_display"]) == ["Working", "Not Working"]
    assert labels(pdi["multi_function_display"]) == ["Ok", "Not Ok"]
    assert "Not Able to Check" not in labels(ev["cruise_control"])
    # each app's own questions only
    assert "charger" in ev and "charger" not in pdi and "charger" not in used
    assert "car_purchase_invoice" in used and "form_21" in pdi and "form_21" not in used


def test_system_fields_take_clappias_place_and_rules_point_at_our_keys(admin):
    put_all(admin)
    start, end, booking = live_fields("start"), live_fields("end"), live_fields("booking")
    assert start["selfie"].label == "Your photo with car's number plate"
    assert start["amount"].show_if == {"==": [{"var": "start.inspection_45_minutes_delayed"},
                                              "yes"]}
    assert [o["label"] for o in end["payment_mode"].config["options"]] == ["Cash", "UPI"]
    from apps.forms.models import FormAsset

    for key, name in (("pay_qr", "Payment QR"), ("review_qr", "Google review QR")):
        assert end[key].config["asset"] == str(FormAsset.objects.get(name=name).id)
    assert booking["service_history_taken"].show_if == {
        "==": [{"var": "booking.inspection_type"}, "used_car"]}
    assert booking["final_amount"].type == "currency"
    assert live_fields("pdi")["chassis_no"].label == "Chassis Number"


def test_each_inspection_gets_its_report_in_the_pdi_design(admin, s3):  # noqa: F811
    from apps.platform.setup import reports
    from apps.reports.models import PdfTemplate

    put_all(admin)
    for key, *_ in forms.INSPECTIONS:
        assert reports.apply(admin, key).startswith("published")
        assert reports.apply(admin, key) == "kept"
        assert reports.apply(admin, key, force=True) == "unchanged"
    def latest(k):
        v = PdfTemplate.objects.get(form__key=k).versions.filter(
            status="published").order_by("-number").first()
        assert v is not None
        return v.definition
    d = latest("used_car")
    titles = [p["title"] for p in d["pages"]]
    assert titles[:3] == ["Cover", "Summary", "Detailed report"] and "Exterior Body" in titles
    assert d["filename"].endswith("PPI.pdf") and "Battery, Charger and Hood" not in titles
    ev = latest("ev")
    assert "Battery, Charger and Hood" in [p["title"] for p in ev["pages"]]


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


def test_the_production_setup_never_imports_demo_code():
    """F-004: setup_platform runs on production; the demo modules are for test servers."""
    import ast
    from pathlib import Path

    setup = Path(__file__).resolve().parents[1] / "setup"
    for path in [*setup.glob("*.py"), setup.parent / "management/commands/setup_platform.py"]:
        if path.name == "testdata.py":                     # test servers only
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import | ast.ImportFrom)
                     else [])
            module = getattr(node, "module", "") or ""
            assert not any("demo" in n for n in [module, *names]), path.name
