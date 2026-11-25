"""Key Checks: set up by Admin per form version, worked out from answers, filled by Ops."""
from typing import Any

import pytest

from apps.bookings.models import BookingActivity
from apps.reports.context import Source

from .test_scoring import V, override, run, scores, senv  # noqa: F401
from .test_submissions import publish_form

pytestmark = pytest.mark.django_db

KC: list[dict[str, Any]] = [
    {"key": "accident", "label": "Accident history", "type": "text", "default": "None seen"},
    {"key": "odo", "label": "Odometer", "type": "number"},
    {"key": "body", "label": "Body", "type": "linked", "fields": ["door", "inspection.paint"],
     "combine": "join", "separator": " / "},
    {"key": "summary", "label": "Summary", "type": "linked", "fields": ["door", "paint"],
     "combine": "template", "template": "Door {door}, paint {inspection.paint}"},
    {"key": "seat_kc", "label": "Seat", "type": "linked", "fields": ["seat"],
     "default": "Not looked at", "in_report": False},
    {"key": "dented", "label": "Dented", "type": "rule",
     "rule": {"==": [V("inspection.door"), "dent"]}, "true_label": "Dent", "false_label": "Clean"},
]


@pytest.fixture
def kenv(senv):
    d = senv.admin.post(f"/api/v1/forms/{senv.form_id}/drafts").json()["id"]
    r = senv.admin.patch(f"/api/v1/form-versions/{d}/key-checks", {"key_checks": KC},
                         format="json")
    assert r.status_code == 200, r.json()
    publish_form(senv.admin, senv.form_id)
    senv.kc_version = d
    return senv


def values(insp):
    return {k: v["value"] for k, v in scores(insp)["key_checks"].items()}


def test_key_checks_are_worked_out_from_the_answers(kenv):
    _, insp = run(kenv, {"door": "dent", "paint": "ok"})
    assert values(insp) == {"accident": "None seen", "odo": "", "body": "Dent / Ok",
                            "summary": "Door Dent, paint Ok", "seat_kc": "Not looked at",
                            "dented": "Dent"}


def test_ops_text_wins_stays_after_edits_and_can_be_reset(kenv):
    b, insp = run(kenv, {"door": "dent", "paint": "ok"})
    r = override(kenv.ops, insp, {"key_checks": {"body": "Dent, repainted"}})
    assert r.status_code == 200, r.json()
    s = scores(insp)["key_checks"]["body"]
    assert s == {"auto": "Dent / Ok", "value": "Dent, repainted", "edited": True}
    insp.refresh_from_db()
    kenv.ops.patch(f"/api/v1/inspections/{insp.id}", {
        "answers": {"inspection": {"door": "ok"}}, "row_version": insp.row_version},
        format="json")
    s = scores(insp)["key_checks"]
    assert s["body"]["value"] == "Dent, repainted" and s["body"]["auto"] == "Ok / Ok"
    assert s["dented"]["value"] == "Clean"                       # not edited: follows answers
    override(kenv.ops, insp, {"key_checks": {"body": None}})
    assert scores(insp)["key_checks"]["body"] == {"auto": "Ok / Ok", "value": "Ok / Ok",
                                                  "edited": False}
    row = BookingActivity.objects.filter(kind="key_checks_changed").order_by("id").first()
    assert row is not None and row.changes == {"check.body": ["Dent / Ok", "Dent, repainted"]}
    ops_rows = kenv.ops.get(f"/api/v1/bookings/{b['id']}/activity").json()
    mine = [x for x in ops_rows if x["kind"] == "key_checks_changed"]   # newest first
    assert mine[-1]["changes"] == {"check.body": ["Dent / Ok", "Dent, repainted"]}
    assert not BookingActivity.objects.filter(kind="ratings_changed").exists()


def test_key_check_text_waits_for_the_expert_to_submit(kenv):
    from apps.bookings.models import Booking
    b, insp = run(kenv, {})
    Booking.objects.filter(pk=b["id"]).update(stage="in_progress")   # still being inspected
    r = override(kenv.ops, insp, {"key_checks": {"body": "Dent"}})
    assert r.status_code == 409 and r.json()["code"] == "NOT_SUBMITTED"


@pytest.mark.parametrize("body", [{"key_checks": {"ghost": "x"}}, {"key_checks": {"body": 3}},
                                  {"key_checks": {"body": "x" * 501}}, {"key_checks": []}])
def test_bad_key_check_text_is_refused(kenv, body):
    _, insp = run(kenv, {})
    r = override(kenv.ops, insp, body)
    assert r.status_code == 400 and r.json()["code"] == "INVALID_OVERRIDES"


def test_experts_never_get_key_checks(kenv):
    from .conftest import create
    from .test_submissions import assign, start

    _, insp = run(kenv, {"door": "dent"})
    assert override(kenv.expert, insp, {"key_checks": {"body": "x"}}).status_code == 403
    b = create(kenv.ops, booking_id="KC1").json()
    assign(kenv, b)
    assert "key_checks" not in start(kenv.expert, b).json()["form"]


def test_key_checks_are_validated_draft_only_and_copied_to_new_drafts(kenv):
    admin, v = kenv.admin, kenv.kc_version
    assert admin.patch(f"/api/v1/form-versions/{v}/key-checks", {"key_checks": KC},
                       format="json").status_code == 409          # published: locked
    d = admin.post(f"/api/v1/forms/{kenv.form_id}/drafts").json()["id"]
    assert admin.get(f"/api/v1/form-versions/{d}").json()["key_checks"] == KC
    for bad in ([{**KC[0], "type": "photo"}], [KC[0], KC[0]],
                [{**KC[3], "template": "{door} {colour}"}], [{**KC[0], "surprise": 1}],
                [{**KC[2], "fields": []}], "nope"):
        r = admin.patch(f"/api/v1/form-versions/{d}/key-checks", {"key_checks": bad},
                        format="json")
        assert r.status_code == 400 and r.json()["code"] == "INVALID_KEY_CHECKS", bad


def test_publish_refuses_a_key_check_on_a_missing_field(kenv):
    admin = kenv.admin
    d = admin.post(f"/api/v1/forms/{kenv.form_id}/drafts").json()["id"]
    assert admin.patch(f"/api/v1/form-versions/{d}/key-checks", {"key_checks": [
        {"key": "gone", "label": "X", "type": "linked", "fields": ["ghost"]}]},
        format="json").status_code == 200
    issues = admin.post(f"/api/v1/form-versions/{d}/validate").json()["issues"]
    assert ("key_checks.gone.fields", "UNKNOWN_FIELD") in {(i["path"], i["code"]) for i in issues}


def test_the_report_gets_key_checks_admin_left_in(kenv):
    b, insp = run(kenv, {"door": "dent", "paint": "ok"})
    override(kenv.ops, insp, {"key_checks": {"accident": "Minor, rear"}})
    insp.refresh_from_db()
    src = Source(booking=insp.booking, insp=insp)
    checks = src.values()["check"]
    assert checks["accident"] == "Minor, rear" and "seat_kc" not in checks
    assert src.cell("check.body").text == "Dent / Ok"


def test_integrations_send_key_checks(kenv):
    from apps.integrations.values import _kc_value

    _, insp = run(kenv, {"door": "dent"})
    override(kenv.ops, insp, {"key_checks": {"odo": "48,000"}})
    s = scores(insp)
    assert _kc_value(KC[1], s) == 48000 and _kc_value(KC[0], s) == "None seen"


def test_report_templates_may_show_key_checks(kenv):
    from apps.reports import placeholders

    placeholders.check("Accident: {{ check.accident }}", "header")      # allowed, not refused
    _, insp = run(kenv, {"door": "dent", "paint": "ok"})
    insp.refresh_from_db()
    src = Source(booking=insp.booking, insp=insp)
    assert placeholders.render("{{ check.body }}", src.values()) == "Dent / Ok"


def test_only_inspection_forms_take_key_checks(kenv):
    from apps.forms.models import Form

    booking_form = Form.objects.get(type="booking")
    d = kenv.admin.post(f"/api/v1/forms/{booking_form.id}/drafts").json()["id"]
    r = kenv.admin.patch(f"/api/v1/form-versions/{d}/key-checks", {"key_checks": KC[:1]},
                         format="json")
    assert r.status_code == 400 and r.json()["code"] == "INVALID_KEY_CHECKS"


# ---------------------------------------------------------------- report rows and integrations

def test_report_table_rows_show_key_checks_with_their_tone(kenv):
    from apps.reports.context import table_rows

    def rows(answers, overrides=None):
        _, insp = run(kenv, answers)
        if overrides:
            override(kenv.ops, insp, {"key_checks": overrides})
        insp.refresh_from_db()
        src = Source(booking=insp.booking, insp=insp)
        part = {"source": {"kind": "fields", "rows": [
            {"field": "check.dented"}, {"field": "check.seat_kc"}, {"field": "check.gone"},
            {"field": "check.odo"}, {"field": "check.odo", "fallback": "Not read"},
            {"field": "check.accident", "label": "Accidents"}]}}
        return table_rows(src, part, src.values())

    dent = rows({"door": "dent", "paint": "ok"})
    assert [(r["label"], r["text"], r["tone"], r["empty"]) for r in dent] == [
        ("Dented", "Dent", "bad", False),            # a Yes/No: "yes" is the problem
        ("Odometer", "Not read", None, True),        # empty: only the row with a fallback
        ("Accidents", "None seen", None, False)]     # label from the row; seat_kc left out
    assert rows({"door": "ok", "paint": "ok"})[0]["tone"] == "ok"
    assert rows({"door": "ok", "paint": "ok"}, {"dented": "Not sure"})[0]["tone"] is None


def test_integrations_list_and_send_each_key_check(kenv):
    from apps.forms.models import Form
    from apps.integrations import values
    from apps.integrations.models import Delivery, Integration

    refs = {c["ref"]: c["type"] for c in values.catalogue(Form.objects.get(pk=kenv.form_id))}
    assert refs["result.key_check.odo"] == "number" and refs["result.key_check.body"] == "text"
    b, insp = run(kenv, {"door": "dent", "paint": "ok"})
    override(kenv.ops, insp, {"key_checks": {"odo": "about 40k"}})
    d = Delivery(integration=Integration(form_id=kenv.form_id), event="pdf.ready",
                 booking_uuid=b["id"], booking_ref=b["booking_id"])
    r = values.Resolver(d)
    assert r.get("result.key_check.odo") == "about 40k"     # a Number one that isn't a number
    assert r.get("result.key_check.nope") is None
    assert {"name": "Accident history", "value": "None seen"} in r.get("result.key_checks")


@pytest.mark.parametrize("bad, message", [
    ({"label": " "}, "label must be text"),
    ({"in_report": "yes"}, "in_report must be true or false"),
    ({"type": "linked", "fields": ["door"], "combine": "both"}, "combine must be join or template"),
    ({"type": "rule", "rule": {}}, "the rule is required"),
])
def test_bad_key_check_settings_are_named(bad, message):
    from apps.scoring import keychecks

    kc = {"key": "x1", "label": "X", "type": "text", **bad}
    with pytest.raises(ValueError, match=message):
        keychecks.validate([kc])


def test_publish_reports_stored_key_checks_that_no_longer_validate():
    from types import SimpleNamespace
    from unittest import mock

    from apps.scoring import keychecks

    version = SimpleNamespace(form=SimpleNamespace(ns="inspection"), key_checks="not a list")
    with mock.patch("apps.forms.rules._known_fields", return_value={}):
        assert keychecks.issues(version)[0][1] == "INVALID_KEY_CHECKS"
