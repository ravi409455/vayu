"""The setup's forms, each built from its own Clappia app read-out (apps/platform/setup/data)."""
import pytest

from apps.accounts.models import Role, User
from apps.forms.models import Field, Form
from apps.media.tests.conftest import s3  # noqa: F401  (in-memory storage for the logo)
from apps.platform.setup import build, forms, lists

pytestmark = pytest.mark.django_db


@pytest.fixture(scope="module")
def built(django_db_setup, django_db_blocker):
    """The whole setup, put once for this file (it takes several seconds): each test then runs in
    its own savepoint on top of it, so whatever one changes is undone for the next. Tests that
    need an empty platform live in test_setup_runs.py."""
    from django.conf import settings
    from django.db import transaction
    from moto import mock_aws

    from apps.media import storage

    with django_db_blocker.unblock(), mock_aws():        # the QR pictures go to the file store
        storage.client().create_bucket(Bucket=settings.S3_BUCKET)
        outer = transaction.atomic()
        outer.__enter__()
        try:
            user = User.objects.create_user(username="setup_admin", password="x" * 12,
                                            role=Role.ADMIN)
            put_all(user)
            yield user
        finally:
            transaction.set_rollback(True)
            outer.__exit__(None, None, None)


@pytest.fixture
def admin(built):
    return built


def put_all(admin, force=False) -> dict:
    lists.apply()
    out = {"booking": build.apply(admin, build.system_form("booking"), forms.booking(),
                                  force=force),
           "start": build.apply(admin, build.system_form("start"), forms.start(), force=force),
           "end": build.apply(admin, build.system_form("end"), forms.end(admin), force=force)}
    build.library(admin, forms.library(admin), force=force)
    for key, name, itype, _ in forms.INSPECTIONS:
        spec, extra = forms.inspection(key, admin)
        out[key] = build.apply(admin, build.ensure_form(admin, key=key, name=name, itype=itype),
                               spec, extra, force=force)
    return out


def live_fields(key):
    v = Form.objects.get(key=key).versions.filter(status="published").order_by("-number").first()
    return {f.key: f for f in Field.objects.filter(version=v)}


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


def test_shared_questions_are_one_library_item_and_own_ones_stay_per_form(admin):
    """Owner, 2026-11-26 (docs/common-sections): what the forms share lives once in the library."""
    from apps.forms.models import LibraryItem, Section

    put_all(admin)
    pdi, used, ev = live_fields("pdi"), live_fields("used_car"), live_fields("ev")
    labels = lambda f: [o["label"] for o in f.config["options"]]  # noqa: E731
    # one shared section, linked in all three, the same questions and answers everywhere
    body = LibraryItem.objects.get(kind="section", key="exterior_body")
    linked = Section.objects.filter(library_item=body, version__status="published")
    assert sorted(linked.values_list("version__form__key", flat=True)) == ["ev", "pdi", "used_car"]
    for f in (pdi, used, ev):
        assert labels(f["multi_function_display"]) == ["Ok", "Not Ok"]            # owner's pick
        assert "Not Able to Check" in labels(f["cruise_control"])
        assert labels(f["stepney_tyre_shape"]) == ["Ok", "Damaged", "Not Applicable",
                                                   "Not Able to Check"]
        assert f["axle_rotating_video"].section.title == "Axle"     # was Used Car only
        assert f["chassis_no"].section.library_item_id is None      # built in, not library
    # fuel-car questions are shared by PDI and Used Car; EV has its own
    fuel = LibraryItem.objects.get(kind="section", key="fuel_filler_flap")
    assert sorted(Section.objects.filter(library_item=fuel, version__status="published")
                  .values_list("version__form__key", flat=True)) == ["pdi", "used_car"]
    assert ev["charger_flap"].section.title == "Charger Flap" and "charger_flap" not in pdi
    assert "fuel_filler_flap" in pdi and "fuel_filler_flap" not in ev
    # a section that stays separate shares its plain questions as library fields
    assert pdi["engine_oil_cap"].library_item_id == used["engine_oil_cap"].library_item_id
    assert pdi["engine_oil_cap"].library_item_id is not None
    assert pdi["engine_oil_cap"].section.title == "Engine"
    assert used["engine_oil_cap"].section.title.startswith("Engine (")
    # Used Car keeps its own Registration Certificate ("Expired"); PDI and EV share one
    assert "Expired" in labels(used["registration_certificate"])
    assert used["registration_certificate"].library_item_id is None
    assert pdi["registration_certificate"].library_item_id == \
        ev["registration_certificate"].library_item_id is not None
    assert "car_purchase_invoice" in used and "form_21" in pdi and "form_21" not in used


def test_ops_own_page_comes_first_and_experts_never_see_it(admin):
    """Owner, 2026-11-26: "Additional Checks" (Expert Comments, five named Key Checks) is Ops'."""
    from apps.forms.access import STAGES, levels_for
    from apps.forms.models import Page

    put_all(admin)
    for key in ("pdi", "used_car", "ev"):
        v = Form.objects.get(key=key).versions.get(status="published")
        pages = list(Page.objects.filter(version=v).order_by("order"))
        assert pages[0].title == "Additional Checks" and not pages[0].gate
        first = next(p for p in pages if p.title == "Car Details")
        assert first.gate                        # the car's details open the rest of the form
        assert [s.title for s in pages[0].sections.order_by("order")] == [
            "Expert Comments", "Additional Details", "Key Checks"]
        mine = ["expert_comments", "manufacturing_date", "price_estimate"] + [
            f"key_check_{n}_{x}" for n in range(1, 6) for x in ("label", "value")]
        if key == "used_car":             # its own Ops-only page of service history comes next
            assert pages[1].title == "Service History Details"
            mine += ["last_service_date", "total_services", "service_history_analysis"]
        for stage in STAGES:
            levels = levels_for(v, "expert", stage)
            assert {levels[k] for k in mine} == {"hidden"}, (key, stage)
        for stage in ("submitted", "completed"):
            assert {levels_for(v, "ops", stage)[k] for k in mine} == {"edit"}
        # the Key Checks are these and no others; each starts from its own value
        want = ["Tyre Manufacturing Year", "Scratches And Dents", "Repainted Panels",
                "Rusting in Body"]
        assert [kc["label"] for kc in v.key_checks] == (
            ["Accidental History"] if key == "used_car" else []) + want
        assert {kc["label"]: kc["default"] for kc in v.key_checks}["Tyre Manufacturing Year"] \
            == "2026"
    # Manufacturing Date is asked on PDI and EV, Price Estimate on a Used Car (one shared section)
    from django.utils import timezone

    from apps.forms.rules import evaluate_form, spec_from_version

    for key in ("pdi", "used_car", "ev"):
        spec = spec_from_version(Form.objects.get(key=key).versions.get(status="published"))
        r = evaluate_form(spec, {"booking": {"inspection_type": key}, "inspection": {}},
                          timezone.localdate().isoformat())
        assert r.visible["manufacturing_date"] is (key != "used_car")
        assert r.visible["price_estimate"] is (key == "used_car")


def test_body_frame_photos_follow_the_inspection_type(admin):
    """Owner, 2026-11-26: one shared Body Frame; its photos always on a Used Car, on PDI and EV
    only (and then required) when their check finds a problem."""
    from django.utils import timezone

    from apps.forms.rules import evaluate_form, spec_from_version

    put_all(admin)
    today, photo = timezone.localdate().isoformat(), "driver_side_a_pillar_image"
    for key, always in (("pdi", False), ("ev", False), ("used_car", True)):
        spec = spec_from_version(Form.objects.get(key=key).versions.get(status="published"))
        for answer, shown in ((["ok"], always), (["accidental"], True)):
            r = evaluate_form(spec, {"booking": {"inspection_type": key},
                                     "inspection": {"driver_side_a_pillar": answer}}, today)
            assert (r.visible[photo], r.required[photo]) == (shown, shown), (key, answer)


def test_paint_gauge_gear_panel_and_wiper_questions(admin):
    put_all(admin)
    pdi, used, ev = live_fields("pdi"), live_fields("used_car"), live_fields("ev")
    labels = lambda f: [o["label"] for o in f.config["options"]]  # noqa: E731
    for f in (pdi, used, ev):
        gauge = [x for x in f.values() if x.key.endswith("_paint_gauge_reading")]
        assert len(gauge) == 11 and all(
            x.required and not x.show_if and x.config == {"max_count": 2, "capture": "camera"}
            for x in gauge)
        door, reading = f["driver_front_door"], f["driver_front_door_paint_gauge_reading"]
        assert reading.section_id == door.section_id and reading.order == door.order + 1
        assert labels(f["wiper_washer_spray"]) == ["Working", "Not Working"]
        assert labels(f["rear_wiper"]) == ["Working", "Not Working", "Not Applicable"]
        assert f["rear_wiper"].order == f["wiper"].order + 2
        assert "Damaged" in labels(f["passenger_side_view_mirror_housing"])
        assert not [x.label for x in f.values() if "Board Board" in x.label
                    or "PassengerSide" in x.label or "(electrical and interior)" in x.label]
    for f in (pdi, used):
        gear = f["gear_shifting_panel"]
        assert gear.type == "photo" and gear.required
        assert gear.section.title == "Engine and Fuel Details"
        assert gear.order == f["transmission_type"].order + 1
    assert "gear_shifting_panel" not in ev


def test_names_answers_and_colours_follow_the_customer_review(admin):
    """Owner, 2026-11-27: the label names the part, the answer says the result; every check has
    its colours; no rule points at an answer that is no longer there."""
    import json
    import re

    put_all(admin)
    opts = lambda f: [(o["label"], o.get("tone")) for o in f.config["options"]]  # noqa: E731
    for key in ("pdi", "used_car", "ev"):
        f = live_fields(key)
        by_label = {x.label: x for x in f.values()}
        assert opts(by_label["Central Lock"])[:2] == [("Working", "ok"), ("Not Working", "bad")]
        assert opts(by_label["Rear Defogger Vent"])[0] == ("Working", "ok")
        assert opts(by_label["Front Driver Side Seat Belt"]) == [("Ok", "ok"), ("Not Ok", "bad")]
        assert opts(by_label["Generator / Alternator State"]) == [
            ("Good", "ok"), ("High Voltage", "warn"), ("Faulty", "bad")]
        assert by_label["AC Cool Temperature"].config["unit"] == "°C"
        depth = by_label["Driver Front Tyre Tread Depth (mm)"]
        assert depth.type == "number" and depth.config["unit"] == "mm" and depth.required
        assert by_label["Stepney Tyre Tread Depth (mm)"].show_if      # only when there is one
        assert "Tool Kit" in {x.section.title for x in f.values()}
        gone = [x.label for x in f.values() if re.search(
            r"De fogger|Weird|^Check (Gear|4x4|for|Onboard)|^Match |7 Seater|Equipments", x.label)]
        assert not gone, gone
        plain = {x.label for x in f.values() if x.type in ("single_choice", "multi_choice")
                 and not x.config["options"][0].get("tone")}
        assert plain <= {"Car Company", "Car Registered State", "Fuel Type", "Transmission Type",
                         "CNG Fitting", "Tyre Type", "Rim Type",
                         "Inspection 45 Minutes Delayed?", "Payment Mode"}, plain
        for x in f.values():                # a rule only names answers its question still has
            refs = re.findall(r'"inspection\.([a-z0-9_]+)"', json.dumps(x.show_if or {}))
            keys = {o["key"] for ref in refs for o in f[ref].config.get("options", [])}
            named = set(re.findall(r'"([a-z0-9_]+)"', json.dumps(x.show_if or {}))) - {
                "var", "in", "or", "some", "and", "inspection", *refs,
                "used_car", "pdi", "ev"}                    # the inspection type, not an answer
            if keys:
                assert {n for n in named if "." not in n} <= keys | {""}, (x.label, named)


def test_a_shared_section_never_depends_on_a_question_outside_it(admin):
    from apps.forms.library import check_self_contained, validate_section_definition

    lib = forms.library(admin)
    for item in lib["sections"].values():
        check_self_contained("section", validate_section_definition(item["definition"]))
    for item in lib["fields"].values():
        check_self_contained("field", item["definition"])


def test_a_late_start_is_a_library_page_of_every_inspection_form_after_ops_pages(admin):
    """Owner, 2026-11-26: "Inspection Delay" is a page of the main form (one library section),
    after Additional Checks and before Car Details; on Yes the payment is taken as on the
    wrap-up. The check-in keeps only selfie, place and time."""
    from django.utils import timezone

    from apps.forms.models import FormAsset, Page
    from apps.forms.rules import evaluate_form, spec_from_version

    put_all(admin)
    assert set(live_fields("start")) == {"selfie", "checkin_gps", "checkin_time"}
    paying = ("delay_amount", "delay_payment_mode", "delay_pay_qr", "delay_payment_screenshot")
    for key in ("pdi", "used_car", "ev"):
        v = Form.objects.get(key=key).versions.get(status="published")
        titles = [p.title for p in Page.objects.filter(version=v).order_by("order")]
        at = titles.index("Inspection Delay")
        assert titles[at - 1] == ("Service History Details" if key == "used_car"
                                  else "Additional Checks")
        assert titles[at + 1] == "Car Details"
        mine = live_fields(key)
        sec = mine["inspection_45_minutes_delayed"].section
        assert sec.library_item is not None and not sec.access
        assert mine["delay_amount"].label == "Amount (Pending + 500)"
        assert mine["delay_amount"].type == "number" and mine["delay_amount"].config == {
            "min": 500}
        assert [o["label"] for o in mine["delay_payment_mode"].config["options"]] == [
            "Cash", "UPI"]
        assert mine["delay_pay_qr"].config["asset"] == str(
            FormAsset.objects.get(name="Payment QR").id)
        spec, today = spec_from_version(v), timezone.localdate().isoformat()

        def shown(spec=spec, key=key, today=today, **answers) -> set[str]:
            r = evaluate_form(spec, {"booking": {"inspection_type": key},
                                     "inspection": answers}, today)
            return {k for k in paying if r.visible[k]}

        assert shown(inspection_45_minutes_delayed="no") == set()
        assert shown(inspection_45_minutes_delayed="yes") == set(paying[:2])
        assert shown(inspection_45_minutes_delayed="yes", delay_payment_mode="cash") == set(
            paying[:2])
        assert shown(inspection_45_minutes_delayed="yes", delay_payment_mode="upi") == set(
            paying)
        # a payment screenshot is ours: never in the report, its downloads or a ZIP
        assert mine["delay_payment_screenshot"].config["hide_from_customer"] is True
        assert live_fields("end")["payment_screenshot"].config["hide_from_customer"] is True
        # the built-in chassis number is scanned
        assert mine["chassis_no"].config.get("scan") is True
        if key != "ev":
            assert mine["engine_number"].config.get("scan") is None


def test_system_fields_take_clappias_place_and_rules_point_at_our_keys(admin):
    put_all(admin)
    start, end, booking = live_fields("start"), live_fields("end"), live_fields("booking")
    assert start["selfie"].label == "Your photo with car's number plate"
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
    # the issues have a page to themselves; Key Checks, Ops' own and the comment share the next
    assert titles[:4] == ["Cover", "Key checks", "Issues found", "Detailed report"]
    # two small sections share a page (each keeps its heading); every other section has its own
    assert "Transmission and Clutch Pedal and Axle" in titles and "Axle" not in titles
    assert "Battery and Charging and OBD Scan" in titles and "OBD Scan" not in titles
    issues = next(p for p in d["pages"] if p["title"] == "Issues found")
    assert "style_rules" not in issues["parts"][1]          # no row is highlighted
    assert "Exterior Body" in titles and "Fuel Filler Flap" not in titles    # prints with its parent
    assert not {"Expert Comments", "Additional Checks"} & set(titles)        # Ops' page: no page
    assert d["filename"].endswith("PPI.pdf") and "Battery, Charger and Hood" not in titles
    ev = latest("ev")
    assert "Battery, Charger and Hood" in [p["title"] for p in ev["pages"]]


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
