"""The setup's forms, each built from its own Clappia app read-out (apps/core/setup/data)."""
import pytest

from apps.accounts.models import Role, User
from apps.core.setup import build, forms, lists
from apps.forms.models import Field, Form
from apps.media.tests.conftest import s3  # noqa: F401  (in-memory storage for the logo)

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin():
    return User.objects.create_user(username="setup_admin", password="x" * 12, role=Role.ADMIN)


def put_all(admin) -> dict:
    lists.apply()
    out = {"booking": build.apply(admin, build.system_form("booking"), forms.booking()),
           "start": build.apply(admin, build.system_form("start"), forms.start()),
           "end": build.apply(admin, build.system_form("end"), forms.end(admin))}
    for key, name, itype, _ in forms.INSPECTIONS:
        spec, extra = forms.inspection(key)
        out[key] = build.apply(admin, build.ensure_form(admin, key=key, name=name, itype=itype),
                               spec, extra)
    return out


def live_fields(key):
    v = Form.objects.get(key=key).versions.filter(status="published").order_by("-number").first()
    return {f.key: f for f in Field.objects.filter(version=v)}


def test_every_form_publishes_and_a_second_run_changes_nothing(admin):
    first = put_all(admin)
    assert all(r.startswith("published") for r in first.values()), first
    assert put_all(admin) == {k: "unchanged" for k in first}


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
    from apps.core.setup import reports
    from apps.reports.models import PdfTemplate

    put_all(admin)
    for key, *_ in forms.INSPECTIONS:
        assert reports.apply(admin, key).startswith("published")
        assert reports.apply(admin, key) == "unchanged"
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
