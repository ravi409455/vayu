"""The data migration for form types, run for real: a database as it was before (one check-in and
wrap-up "ops" form, ops answers, ops references in rules / library / PDF rows) is migrated and
checked."""
import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("forms", "0009_form_type_step1"),
          ("bookings", "0004_scoring"), ("reports", "0002_render_started")]
AFTER = [("forms", "0012_alter_field_type_alter_fieldkey_type_alter_form_type"),
         ("bookings", "0006_split_ops_answers"), ("reports", "0003_ops_references")]
PAID = {"==": [{"var": "ops.taking_payment"}, True]}


def migrate(targets):
    executor = MigrationExecutor(connection)
    executor.migrate(targets)
    return MigrationExecutor(connection).loader.project_state(targets).apps


@pytest.fixture
def old_world():
    from apps.accounts.models import User
    from apps.forms.models import Form

    Form.objects.all().delete()                  # the system forms made for the current schema
    User.objects.create_user(username="e", password="x", role="expert")   # made now: users keep their schema
    apps = migrate(BEFORE)
    yield apps
    migrate(AFTER)                               # leave the database at the newest state
    from django.contrib.contenttypes.models import ContentType

    ContentType.objects.clear_cache()            # later tests flush the database


def build_old_data(apps):
    Form, Version = apps.get_model("forms", "Form"), apps.get_model("forms", "FormVersion")
    Page, Section = apps.get_model("forms", "Page"), apps.get_model("forms", "Section")
    Field, Check = apps.get_model("forms", "Field"), apps.get_model("forms", "VersionCheck")
    Library = apps.get_model("forms", "LibraryItem")
    MasterList = apps.get_model("forms", "MasterList")
    User = apps.get_model("accounts", "User")
    Booking, Inspection = apps.get_model("bookings", "Booking"), apps.get_model(
        "bookings", "Inspection")
    Template = apps.get_model("reports", "PdfTemplate")
    TemplateVersion = apps.get_model("reports", "PdfTemplateVersion")

    MasterList.objects.create(key="inspection_type", name="Inspection type")
    booking = Form.objects.create(key="booking", kind="booking", type="", name="Booking")
    bv = Version.objects.create(form=booking, number=1, status="published")
    bp = Page.objects.create(version=bv, title="Page 1")
    bs = Section.objects.create(version=bv, page=bp, title="S")
    Field.objects.create(version=bv, section=bs, key="inspection_type", label="Type",
                         type="master_list", config={"list": "inspection_type"})

    ops = Form.objects.create(key="checkin", kind="ops", type="", name="Check-in and wrap-up")
    ov = Version.objects.create(form=ops, number=1, status="published")
    before = Page.objects.create(version=ov, title="Check-in", slot="before")
    after = Page.objects.create(version=ov, title="Wrap-up", slot="after", order=1,
                                show_if={"!!": [{"var": "ops.selfie"}]})
    sb = Section.objects.create(version=ov, page=before, title="Check-in")
    sa = Section.objects.create(version=ov, page=after, title="Payment")
    Field.objects.create(version=ov, section=sb, key="selfie", label="Selfie", type="photo")
    Field.objects.create(version=ov, section=sa, key="taking_payment", label="Paying?",
                         type="yes_no")
    Field.objects.create(version=ov, section=sa, key="payment_mode", label="Mode",
                         type="short_text", show_if=PAID, required_if=PAID)
    Field.objects.create(version=ov, section=sa, key="my_extra", label="Extra", type="derived",
                         config={"rule": {"!!": [{"var": "ops.payment_mode"}]}})
    ov2 = Version.objects.create(form=ops, number=2, status="draft")     # an open draft too
    p2 = Page.objects.create(version=ov2, title="Wrap-up", slot="after")
    s2 = Section.objects.create(version=ov2, page=p2, title="Payment")
    Field.objects.create(version=ov2, section=s2, key="taking_payment", label="Paying?",
                         type="yes_no")

    pdi = Form.objects.create(key="pdi", kind="inspection", type="", name="PDI",
                              inspection_type="pdi")
    pv = Version.objects.create(form=pdi, number=1, status="published")
    pp = Page.objects.create(version=pv, title="P", show_if={"!!": [{"var": "ops.selfie"}]})
    ps = Section.objects.create(version=pv, page=pp, title="S", show_if=PAID)
    Field.objects.create(version=pv, section=ps, key="door", label="Door", type="short_text",
                         show_if=PAID, required_if={"!!": [{"var": ["ops.payment_mode", 0]}]})
    Check.objects.create(version=pv, rule=PAID, message="pay", fields=["door"])
    Library.objects.create(kind="field", key="lib", name="Lib", definition={
        "key": "lib", "label": "L", "type": "short_text", "show_if": PAID})
    template = Template.objects.create(form=pdi)
    TemplateVersion.objects.create(template=template, number=1, status="published", definition={
        "blocks": [{"type": "table", "rows": [{"label": "Mode", "field": "ops.payment_mode"},
                                              {"label": "Door", "field": "inspection.door"}]}]})

    expert = User.objects.get(username="e")
    b = Booking.objects.create(booking_id="B1", inspection_type="pdi", assigned_expert=expert)
    Inspection.objects.create(booking=b, expert=expert, form_version=pv, status="submitted",
                              answers={"inspection": {"door": "ok"}, "ops": {
                                  "selfie": ["m1"], "taking_payment": True, "payment_mode": "upi",
                                  "unplaced": 1}})
    Inspection.objects.create(booking=b, expert=expert, form_version=pv, status="draft")


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_an_old_database_comes_across_with_forms_rules_answers_and_pdf_rows(old_world):
    build_old_data(old_world)
    migrate(AFTER)
    from apps.bookings.models import Inspection
    from apps.forms.models import Field, Form, LibraryItem, MasterList, Page, VersionCheck
    from apps.reports.models import PdfTemplateVersion

    # the one ops form became a start form and a new end form; every page went to its side
    start, end = Form.objects.get(type="start"), Form.objects.get(type="end")
    assert start.key == "checkin" and end.key == "end" and Form.objects.get(
        key="booking").type == "booking" and Form.objects.get(key="pdi").type == "custom"
    assert sorted(start.versions.values_list("number", flat=True)) == [1, 2]
    assert sorted(end.versions.values_list("number", flat=True)) == [1, 2]
    assert end.versions.get(number=1).status == "published"
    assert end.versions.get(number=2).status == "draft"
    assert list(Page.objects.filter(version__form=start).values_list("title", flat=True)) == [
        "Check-in"]
    assert sorted(Page.objects.filter(version__form=end).values_list("title", flat=True)) == [
        "Wrap-up", "Wrap-up"]
    assert sorted(Field.objects.filter(version__form=end, version__number=1)
                  .values_list("key", flat=True)) == ["my_extra", "payment_mode", "taking_payment"]
    assert Field.objects.get(version__form=end, version__number=1, key="payment_mode"
                             ).section.version.form_id == end.id

    # rules everywhere now name the form that owns the key
    paid = {"==": [{"var": "end.taking_payment"}, True]}
    assert Field.objects.get(version__form=end, key="payment_mode", version__number=1
                             ).show_if == paid
    assert Field.objects.get(key="my_extra").config["rule"] == {"!!": [
        {"var": "end.payment_mode"}]}
    door = Field.objects.get(key="door")
    assert door.show_if == paid and door.required_if == {"!!": [{"var": ["end.payment_mode", 0]}]}
    assert door.section.show_if == paid
    assert door.section.page.show_if == {"!!": [{"var": "start.selfie"}]}
    assert Page.objects.get(version__form=end, version__number=1).show_if == {
        "!!": [{"var": "start.selfie"}]}
    assert VersionCheck.objects.get().rule == paid
    assert LibraryItem.objects.get(key="lib").definition["show_if"] == paid
    rows = PdfTemplateVersion.objects.get().definition["blocks"][0]["rows"]
    assert [r["field"] for r in rows] == ["end.payment_mode", "inspection.door"]

    # the booking form picks the type from the custom forms; the old list is gone
    assert Field.objects.get(version__form__key="booking", key="inspection_type"
                             ).type == "form_choice"
    assert not MasterList.objects.filter(key="inspection_type").exists()

    # answers are split by owner and the inspections pin what was live
    done = Inspection.objects.get(status="submitted")
    assert done.answers["inspection"] == {"door": "ok"}
    assert done.answers["start"] == {"selfie": ["m1"], "unplaced": 1}
    assert done.answers["end"] == {"taking_payment": True, "payment_mode": "upi"}
    assert "ops" not in done.answers
    assert done.start_version and done.start_version.form_id == start.id
    assert done.end_version and done.end_version.form_id == end.id
    draft = Inspection.objects.get(status="draft")
    assert draft.answers == {"inspection": {}, "start": {}, "end": {}}
    assert draft.start_version is None                        # nothing was answered to pin
