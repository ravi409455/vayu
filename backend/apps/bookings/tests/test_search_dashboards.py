import csv
import io

import pytest

from .conftest import create
from .test_submissions import GOOD, assign, ienv, start, submit  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture
def many(env):
    rows = [("SA10001", "Asha Rao", "9876500001", "pdi", "2026-10-14"),
            ("VI20002", "Ravi Kumar", "9876500002", "ev", "2026-10-14"),
            ("AD30003", "Asha Verma", "9876500003", "pdi", "2026-10-21"),
            ("CH40004", "Meera Shah", "9999999999", "used_car", "2026-11-03")]
    for bid, name, phone, typ, day in rows:
        assert create(env.ops, booking_id=bid, customer_name=name, customer_phone=phone,
                      inspection_type=typ, inspection_date=day).status_code == 201
    return env


def ids(client, query):
    r = client.get(f"/api/v1/bookings?{query}")
    assert r.status_code == 200
    return sorted(b["booking_id"] for b in r.json()["results"])


def test_search_by_booking_id_partial_and_case_insensitive(many):
    assert ids(many.ops, "search=sa100") == ["SA10001"]
    assert ids(many.ops, "search=ad3") == ["AD30003"]


def test_search_by_customer_name_partial(many):
    assert ids(many.ops, "search=asha") == ["AD30003", "SA10001"]
    assert ids(many.ops, "search=KUMAR") == ["VI20002"]


def test_search_by_phone_needs_four_trailing_digits(many):
    assert ids(many.ops, "search=0002") == ["VI20002"]
    assert ids(many.ops, "search=%2B919876500003") == ["AD30003"]
    assert ids(many.ops, "search=9999") == ["CH40004"]


def test_search_by_car(many):
    assert len(ids(many.ops, "search=victoris")) == 4


def test_search_by_chassis_number_after_submission(ienv, booking):  # noqa: F811
    assign(ienv, booking)
    start(ienv.expert, booking)
    submit(ienv.expert, booking)
    assert ids(ienv.ops, "search=273129") == ["SA37926"]
    assert ids(ienv.ops, "search=MA3YPK") == ["SA37926"]


def test_no_match_and_blank_search(many):
    assert ids(many.ops, "search=zzzz") == []
    assert len(ids(many.ops, "search=")) == 4


def test_filters_combine(many):
    assert ids(many.ops, "type=pdi") == ["AD30003", "SA10001"]
    assert ids(many.ops, "type=pdi&date_from=2026-10-20") == ["AD30003"]
    assert ids(many.ops, "city=delhi&stage=draft&date_to=2026-10-14") == ["SA10001", "VI20002"]
    assert ids(many.ops, "stage=cancelled") == []
    assert ids(many.ops, "type=pdi&search=asha&date_from=2026-10-15") == ["AD30003"]


def test_expert_search_is_limited_to_their_own_jobs(many):
    b = many.ops.get("/api/v1/bookings?search=SA100").json()["results"][0]
    assign(many, b)
    assert ids(many.expert, "search=asha") == ["SA10001"]
    assert ids(many.expert, "") == ["SA10001"]


def test_filter_by_expert(many):
    b = many.ops.get("/api/v1/bookings?search=SA100").json()["results"][0]
    assign(many, b)
    assert ids(many.ops, f"expert={many.expert_user.id}") == ["SA10001"]


# ---------------------------------------------------------------- dashboards

def volume(client, query):
    r = client.get(f"/api/v1/dashboards/volume?{query}")
    assert r.status_code == 200, r.content
    return r.json()["rows"]


def test_volume_by_day_and_type(many):
    rows = volume(many.ops, "group=day&by=type")
    got = {(r["period"], r["key"]): r["count"] for r in rows}
    assert got == {("2026-10-14", "pdi"): 1, ("2026-10-14", "ev"): 1, ("2026-10-21", "pdi"): 1,
                   ("2026-11-03", "used_car"): 1}


def test_volume_by_week_and_month(many):
    month = {(r["period"], r["key"]): r["count"] for r in volume(many.ops, "group=month&by=type")}
    assert month == {("2026-10", "pdi"): 2, ("2026-10", "ev"): 1, ("2026-11", "used_car"): 1}
    week = volume(many.ops, "group=week&by=city")
    assert sum(r["count"] for r in week) == 4
    assert {r["period"] for r in week} == {"2026-W42", "2026-W43", "2026-W45"}


def test_volume_by_city_expert_stage_and_lead_owner(many):
    assert volume(many.ops, "group=month&by=city") == [
        {"period": "2026-10", "key": "delhi", "count": 3},
        {"period": "2026-11", "key": "delhi", "count": 1}]
    b = many.ops.get("/api/v1/bookings?search=SA100").json()["results"][0]
    assign(many, b)
    by_expert: dict = {}
    for r in volume(many.ops, "group=month&by=expert"):
        by_expert[r["key"]] = by_expert.get(r["key"], 0) + r["count"]
    assert by_expert == {str(many.expert_user.id): 1, "": 3}
    assert {r["key"] for r in volume(many.ops, "group=month&by=stage")} == {"draft", "assigned"}
    assert volume(many.ops, "group=month&by=lead_owner")[0]["count"] >= 1


def test_volume_date_range(many):
    rows = volume(many.ops, "group=month&by=type&date_from=2026-11-01")
    assert rows == [{"period": "2026-11", "key": "used_car", "count": 1}]


@pytest.mark.parametrize("query", ["group=year&by=type", "group=day&by=nope", "by=type",
                                   "group=day&by=type&date_from=bad"])
def test_volume_rejects_bad_parameters(many, query):
    assert many.ops.get(f"/api/v1/dashboards/volume?{query}").status_code == 400


def test_csv_export_matches_the_table(many):
    rows = volume(many.ops, "group=day&by=type")
    r = many.ops.get("/api/v1/dashboards/volume?group=day&by=type&export=csv")
    assert r.status_code == 200 and r["Content-Type"].startswith("text/csv")
    parsed = list(csv.DictReader(io.StringIO(r.content.decode())))
    assert [{"period": p["period"], "key": p["key"], "count": int(p["count"])} for p in parsed] == rows


def test_dashboards_need_permissions_and_csv_needs_export(many):
    from apps.accounts.catalog import DEFAULTS

    assert many.expert.get("/api/v1/dashboards/volume?group=day&by=type").status_code == 403
    perms = {k: v for k, v in DEFAULTS["ops"].items() if k != "dashboards.export"}
    assert many.admin.put("/api/v1/roles/ops/permissions", {"permissions": perms},
                          format="json").status_code == 200
    assert many.ops.get("/api/v1/dashboards/volume?group=day&by=type").status_code == 200
    r = many.ops.get("/api/v1/dashboards/volume?group=day&by=type&export=csv")
    assert r.status_code == 403


def test_date_to_bounds_dashboards_and_bad_booking_filters_are_400(many):
    assert volume(many.ops, "group=month&by=type&date_to=2026-10-15") == [
        {"period": "2026-10", "key": "ev", "count": 1},
        {"period": "2026-10", "key": "pdi", "count": 1}]
    assert many.ops.get("/api/v1/bookings?date_from=bad").status_code == 400
    assert many.ops.get("/api/v1/bookings?date_to=2026-13-01").status_code == 400


# ---------------------------------------------------------------- review fixes: no search oracle, safe CSV

def _hide_phone_from_ops(env):
    from apps.forms.models import Form

    form = Form.objects.get(kind="booking")
    d = env.admin.post(f"/api/v1/forms/{form.id}/drafts").json()["id"]
    t = env.admin.get(f"/api/v1/form-versions/{d}").json()
    phone = [f for p in t["pages"] for s in p["sections"] for f in s["fields"]
             if f["key"] == "customer_phone"][0]
    env.admin.patch(f"/api/v1/fields/{phone['id']}", {"access": {"ops": {"completed": "hidden"}}},
                    format="json")
    rv = env.admin.get(f"/api/v1/form-versions/{d}").json()["row_version"]
    assert env.admin.post(f"/api/v1/form-versions/{d}/publish", {"row_version": rv},
                          format="json").status_code == 200


def test_a_role_cannot_search_a_column_at_stages_where_it_may_not_see_it(many):
    from apps.bookings.models import Booking

    assert ids(many.ops, "search=500002") == ["VI20002"]
    _hide_phone_from_ops(many)                        # phone hidden from ops once completed
    Booking.objects.filter(booking_id="VI20002").update(stage="completed")
    assert ids(many.ops, "search=500002") == []         # no confirming a hidden value
    assert ids(many.ops, "search=9876500002") == []
    assert ids(many.admin, "search=500002") == ["VI20002"]
    assert ids(many.ops, "search=500001") == ["SA10001"]          # visible stages still work
    assert ids(many.ops, "search=VI200") == ["VI20002"]         # other columns unaffected


def test_chassis_search_follows_the_same_rule(ienv, booking):  # noqa: F811
    assign(ienv, booking)
    start(ienv.expert, booking)
    submit(ienv.expert, booking)                      # booking is now 'submitted'
    assert ids(ienv.ops, "search=273129") == ["SA37926"]
    from apps.forms.models import Field

    Field.objects.filter(key="chassis_no").update(access={"ops": {"submitted": "hidden"}})
    assert ids(ienv.ops, "search=273129") == []
    assert ids(ienv.admin, "search=273129") == ["SA37926"]


def test_search_with_no_booking_form_finds_nothing_for_non_admins(db, api_as):
    from apps.accounts.models import Role

    ops, _ = api_as(Role.OPS)
    assert ops.get("/api/v1/bookings?search=x").json()["results"] == []


def test_csv_cells_that_look_like_formulas_are_neutralised():
    from apps.bookings.dashboards import csv_safe

    assert csv_safe("=SUM(A1)") == "'=SUM(A1)" and csv_safe("+1") == "'+1"
    assert csv_safe("-2") == "'-2" and csv_safe("@x") == "'@x" and csv_safe("\tx") == "'\tx"
    assert csv_safe("delhi") == "delhi" and csv_safe("") == ""


def test_chassis_is_unsearchable_for_non_admins_when_no_inspection_form_describes_it(many):
    from apps.bookings.models import Booking

    Booking.objects.filter(booking_id="SA10001").update(chassis_no="MA3SECRETCHASSIS1")
    assert ids(many.admin, "search=SECRETCHASSIS") == ["SA10001"]
    assert ids(many.ops, "search=SECRETCHASSIS") == []       # no active inspection form here
