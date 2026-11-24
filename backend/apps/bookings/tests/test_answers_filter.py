"""Bookings filtered by an answer (owner, 2026-11-24): generic, any choice or yes/no field the person
may see; "not filled" finds inspections with no answer (e.g. a payment not yet verified)."""
import pytest

from apps.bookings.models import Inspection
from apps.forms.models import Field

from .conftest import create
from .test_submissions import GOOD, assign, ienv, start, submit  # noqa: F401

pytestmark = pytest.mark.django_db


def done(env, code, **answers):
    b = create(env.ops, booking_id=code).json()
    assign(env, b)
    assert start(env.expert, b).status_code in (200, 201)
    assert submit(env.expert, b).status_code == 200
    if answers:
        i = Inspection.objects.get(booking_id=b["id"])
        i.answers = {**i.answers, "inspection": {**i.answers["inspection"], **answers}}
        i.save()
    return b["id"]


def codes(env, **params):
    r = env.ops.get("/api/v1/bookings", params)
    assert r.status_code == 200, r.json()
    return sorted(b["booking_id"] for b in r.json()["results"])


def test_ops_see_the_fields_they_can_filter_by(ienv):
    rows = {r["field"]: r for r in ienv.ops.get("/api/v1/bookings/answer-fields").json()}
    door = rows["inspection.door"]
    assert door["label"] == "door" and door["type"] == "single_choice"
    assert door["options"] == [{"value": "ok", "label": "Ok"}, {"value": "dent", "label": "Dent"}]
    assert "inspection.odometer" not in rows                        # numbers are not offered


def test_filter_by_a_value_or_by_not_filled(ienv):
    a = done(ienv, "A1")                                          # door: ok
    done(ienv, "B1", door="dent")
    create(ienv.ops, booking_id="C1")                             # not inspected yet
    assert codes(ienv, answer="inspection.door", value="ok") == ["A1"]
    assert codes(ienv, answer="inspection.door", value="dent") == ["B1"]
    Inspection.objects.filter(booking_id=a).update(answers={"inspection": {"door": None}})
    assert codes(ienv, answer="inspection.door", value="__none__") == ["A1"]   # inspected, empty
    assert codes(ienv, answer="inspection.door", value="ok", type="pdi") == []  # with others


def test_unknown_fields_values_and_hidden_fields_are_refused(ienv):
    done(ienv, "A1")
    assert ienv.ops.get("/api/v1/bookings", {"answer": "inspection.nope", "value": "x"}).status_code == 400
    assert ienv.ops.get("/api/v1/bookings", {"answer": "inspection.door", "value": "x"}).status_code == 400
    Field.objects.filter(key="door").update(access={"ops": {"completed": "hidden"}})
    assert "inspection.door" not in {r["field"] for r in ienv.ops.get("/api/v1/bookings/answer-fields").json()}
    assert ienv.ops.get("/api/v1/bookings", {"answer": "inspection.door", "value": "ok"}).status_code == 400


def test_yes_no_and_multi_choice_answers(ienv):
    from apps.bookings import answers_filter
    from apps.bookings.models import Booking
    a = done(ienv, "A1", accident=True, extras=["mats"])
    done(ienv, "B1", accident=False, extras=[])
    rows = [{"field": "inspection.accident", "type": "yes_no", "label": "a",
             "options": [{"value": "true", "label": "Yes"}, {"value": "false", "label": "No"}], "form": "x"},
            {"field": "inspection.extras", "type": "multi_choice", "label": "e",
             "options": [{"value": "mats", "label": "Mats"}], "form": "x"}]
    from unittest import mock

    from apps.forms.models import Form
    for r in rows:
        r["forms"] = [Form.objects.get(key="pdi").id]
    with mock.patch.object(answers_filter, "_rows", return_value=rows):
        qs = Booking.objects.all()
        assert [str(b.id) for b in answers_filter.apply(qs, ienv.admin_user, "inspection.accident", "true")] == [a]
        assert [str(b.id) for b in answers_filter.apply(qs, ienv.admin_user, "inspection.extras", "mats")] == [a]
        assert len(answers_filter.apply(qs, ienv.admin_user, "inspection.extras", "__none__")) == 1


def test_only_people_who_may_see_answers_can_filter(ienv):
    from apps.accounts.models import RolePermission
    RolePermission.objects.filter(role="ops", permission="submissions.view").delete()
    assert ienv.ops.get("/api/v1/bookings/answer-fields").status_code == 403
    assert ienv.ops.get("/api/v1/bookings", {"answer": "inspection.door", "value": "ok"}).status_code == 403


def test_a_key_in_two_forms_is_one_row_and_unused_forms_are_skipped(ienv):
    from apps.bookings import answers_filter
    from apps.forms.models import Form, FormVersion
    pdi = Form.objects.get(key="pdi")
    twin = Form.objects.create(key="ev2", name="EV", type="custom", inspection_type="ev",
                               is_active=True)
    FormVersion.objects.create(form=twin, number=1)                # never published: skipped
    rows = {r["field"]: r for r in answers_filter.fields_for(ienv.admin_user)}
    assert rows["inspection.door"]["form"] == pdi.name
    from unittest import mock

    from apps.bookings.submissions import latest_published
    live = latest_published(pdi)
    with mock.patch.object(answers_filter, "latest_published", side_effect=lambda f: live):
        rows = {r["field"]: r for r in answers_filter.fields_for(ienv.admin_user)}
    assert set(rows["inspection.door"]["form"].split(", ")) == {"EV", pdi.name}   # one row, both
    with mock.patch.object(answers_filter, "hidden_inspection_forms", return_value=[pdi.id, twin.id]):
        assert "inspection.door" not in {r["field"] for r in answers_filter.fields_for(ienv.admin_user)}


def test_answers_in_a_form_that_hides_the_field_are_never_matched(ienv):
    """Same key in two forms, hidden in one: only inspections of the form that shows it count."""
    from unittest import mock

    from apps.bookings import answers_filter
    done(ienv, "A1")                                              # door: ok, in the PDI form
    rows = [{"field": "inspection.door", "type": "single_choice", "label": "door", "form": "x",
             "options": [{"value": "ok", "label": "Ok"}], "forms": [-1]}]   # visible elsewhere only
    with mock.patch.object(answers_filter, "_rows", return_value=rows):
        assert codes(ienv, answer="inspection.door", value="ok") == []
        assert codes(ienv, answer="inspection.door", value="__none__") == []


def test_fields_for_one_inspection_type(ienv):
    """Ops pick a type first: only that type's questions, plus the shared check-in and wrap-up."""
    pdi = {r["field"] for r in ienv.ops.get("/api/v1/bookings/answer-fields", {"type": "pdi"}).json()}
    other = {r["field"] for r in ienv.ops.get("/api/v1/bookings/answer-fields", {"type": "ev"}).json()}
    assert "inspection.door" in pdi and "inspection.door" not in other
    assert {f for f in pdi if not f.startswith("inspection.")} == {f for f in other if not f.startswith("inspection.")}


def test_a_field_hidden_at_the_bookings_stage_now_never_matches(ienv):
    """Visible once completed, hidden while the job waits for files: those bookings don't count."""
    from apps.bookings.models import Booking
    a = done(ienv, "A1")
    Field.objects.filter(key="door").update(access={"ops": {"submitted": "hidden"}})
    Booking.objects.filter(pk=a).update(stage="submitted")
    assert codes(ienv, answer="inspection.door", value="ok") == []
    Booking.objects.filter(pk=a).update(stage="completed")
    assert codes(ienv, answer="inspection.door", value="ok") == ["A1"]


def test_someone_who_sees_only_their_own_inspections_matches_only_those(ienv):
    from apps.bookings import answers_filter
    from apps.bookings.models import Booking
    done(ienv, "A1")
    mine = answers_filter.apply(Booking.objects.all(), ienv.expert_user, "inspection.door", "ok", own=True)
    other = answers_filter.apply(Booking.objects.all(), ienv.make_user("expert"), "inspection.door", "ok", own=True)
    assert [b.booking_id for b in mine] == ["A1"] and list(other) == []
