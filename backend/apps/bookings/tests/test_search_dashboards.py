import csv
import io

import pytest

from .conftest import create, custom_form, publish_draft
from .test_submissions import GOOD, assign, ienv, start, submit  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture
def many(env):
    for key in ("ev", "used_car"):
        publish_draft(env.admin, custom_form(env.admin, key)["id"])
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
    # several experts at once; an unknown id adds nothing; a bad one is refused
    assert ids(many.ops, f"expert={many.expert_user.id},999999") == ["SA10001"]
    assert many.ops.get("/api/v1/bookings?expert=1,x").status_code == 400


def test_filter_by_several_stages(many):
    b = many.ops.get("/api/v1/bookings?search=SA100").json()["results"][0]
    assign(many, b)
    everyone = set(ids(many.ops, ""))
    assert ids(many.ops, "stage=assigned") == ["SA10001"]
    # several stages at once (Ops tick more than one status); an unknown word is refused
    assert set(ids(many.ops, "stage=draft,assigned")) == everyone
    assert set(ids(many.ops, "stage=draft")) == everyone - {"SA10001"}
    assert many.ops.get("/api/v1/bookings?stage=assigned,nope").status_code == 400


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
    assert {p["key"]: p["label"] for p in parsed} == {"ev": "EV", "pdi": "PDI", "used_car": "USED_CAR"}
    assert r["Content-Disposition"] == 'attachment; filename="bookings-by-type.csv"'


def test_csv_names_the_range_and_says_who_or_where(many):
    r = many.ops.get("/api/v1/dashboards/volume?group=month&by=lead_owner&export=csv"
                     "&date_from=2026-10-01&date_to=2026-10-31")
    assert r["Content-Disposition"] == (
        'attachment; filename="bookings-by-lead-owner_2026-10-01_to_2026-10-31.csv"')
    assert {p["label"] for p in csv.DictReader(io.StringIO(r.content.decode()))} == {"Not set"}
    r = many.ops.get("/api/v1/dashboards/volume?group=day&by=city&export=csv&date_to=2026-10-14")
    assert r["Content-Disposition"].endswith('filename="bookings-by-city_to_2026-10-14.csv"')
    assert {p["label"] for p in csv.DictReader(io.StringIO(r.content.decode()))} == {"Delhi"}


def test_key_labels_for_every_split(many):
    from apps.accounts.models import User
    from apps.bookings.dashboards import key_labels

    ops = User.objects.order_by("pk").first()
    assert ops is not None
    assert key_labels("stage", {"draft", "odd", ""}) == {"draft": "Unassigned", "odd": "odd"}
    assert key_labels("type", {"ev", "gone"}) == {"ev": "EV", "gone": "gone"}
    assert key_labels("city", {"delhi", "atlantis"}) == {"delhi": "Delhi", "atlantis": "atlantis"}
    assert key_labels("expert", {str(ops.pk), "abc", "99999"}) == {
        str(ops.pk): ops.name or ops.username, "abc": "abc", "99999": "99999"}
    ops.name = ""
    ops.save()
    assert key_labels("lead_owner", {str(ops.pk)}) == {str(ops.pk): ops.username}


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

    form = Form.objects.get(type="booking")
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
    submit(ienv.expert, booking)                      # no media: booking goes straight to 'completed'
    assert ids(ienv.ops, "search=273129") == ["SA37926"]
    from apps.forms import access
    from apps.forms.models import Field

    # a published version never changes in the app; this test changes one behind its back, so
    # the cached levels (Q5.1) are dropped too
    Field.objects.filter(key="chassis_no").update(access={"ops": {"completed": "hidden"}})
    access._published_levels.cache_clear()
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
    from apps.forms.models import Form

    Form.objects.filter(type="custom").update(is_active=False)     # nothing describes the chassis
    Booking.objects.filter(booking_id="SA10001").update(chassis_no="MA3SECRETCHASSIS1")
    assert ids(many.admin, "search=SECRETCHASSIS") == ["SA10001"]
    assert ids(many.ops, "search=SECRETCHASSIS") == []       # no active inspection form here


# ---------------------------------------------------------------- summary (headline numbers)

def _visit(b, started, submitted, stage):
    from apps.bookings.models import Booking, Inspection
    from apps.forms.models import FormVersion

    booking = Booking.objects.get(booking_id=b)
    Booking.objects.filter(pk=booking.pk).update(stage=stage)
    Inspection.objects.create(booking=booking, expert=booking.assigned_expert or _expert(),
                              form_version=FormVersion.objects.filter(status="published")[0],
                              status="submitted", client_started_at=started, submitted_at=submitted)
    from apps.bookings import timing

    booking.refresh_from_db()
    booking.started_at = started               # the server clock, as Start would stamp it
    timing.stamp_late(booking)
    timing.stamp_duration(booking, submitted)
    booking.save()


def _expert():
    from apps.accounts.models import User

    return User.objects.filter(role="expert").first()


def test_summary_counts_rates_time_on_site_and_on_time(many):
    from datetime import datetime

    from django.utils import timezone

    from apps.bookings.models import Booking

    def at(day, hh, mm):
        return timezone.make_aware(datetime(2026, 10, day, hh, mm))

    e = _expert()
    Booking.objects.filter(booking_id__in=["SA10001", "VI20002"]).update(assigned_expert=e)
    _visit("SA10001", at(14, 15, 40), at(14, 17, 10), "completed")      # slot 15:30: 10 min late, 90 min
    _visit("VI20002", at(14, 16, 0), at(14, 16, 30), "completed")       # 30 min late, 30 min
    Booking.objects.filter(booking_id="AD30003").update(stage="cancelled")
    r = many.ops.get("/api/v1/dashboards/summary?date_from=2026-10-01&date_to=2026-10-31")
    assert r.status_code == 200, r.json()
    p = r.json()["period"]
    assert p == {"bookings": 3, "completed": 2, "cancelled": 1, "completion_rate": 100.0,
                 "avg_minutes": 60, "on_time": 50, "late": 1, "late_pct": 50,
                 "quick": 1, "quick_pct": 50}       # VI20002 (EV): 30 min < 40
    prev = r.json()["previous"]                                         # September: nothing
    assert prev["bookings"] == 0 and prev["completion_rate"] is None and prev["avg_minutes"] is None
    row = r.json()["by_expert"][0]
    assert row["expert"] == e.id and row["bookings"] == 2 and row["on_time"] == 50
    nov = many.ops.get("/api/v1/dashboards/summary?date_from=2026-11-01&date_to=2026-11-30").json()
    assert nov["previous"]["bookings"] == 3 and nov["period"]["bookings"] == 1


def test_summary_defaults_to_the_last_30_days_and_checks_dates(many):
    r = many.ops.get("/api/v1/dashboards/summary")
    assert r.status_code == 200 and r.json()["period"]["bookings"] >= 0
    assert many.ops.get("/api/v1/dashboards/summary?date_from=x").status_code == 400
    bad = "/api/v1/dashboards/summary?date_from=2026-11-02&date_to=2026-11-01"
    assert many.ops.get(bad).status_code == 400
    assert many.expert.get("/api/v1/dashboards/summary").status_code == 403


def test_a_booking_without_a_time_is_left_out_of_on_time(many):
    from apps.bookings.models import Booking
    from apps.bookings.timing import slot as _slot

    b = Booking.objects.get(booking_id="SA10001")
    b.answers = {**b.answers, "inspection_time": None}
    assert _slot(b) is None
    b.inspection_date = None
    assert _slot(b) is None


def test_summary_hides_timing_from_those_who_may_not_see_it(many, monkeypatch):
    from apps.bookings import dashboards

    assert "late" in many.ops.get("/api/v1/dashboards/summary").json()["period"]
    monkeypatch.setattr(dashboards, "scope_for", lambda *a, **k: None)
    body = many.ops.get("/api/v1/dashboards/summary").json()
    for stats in [body["period"], body["previous"], *body["by_expert"]]:
        assert all(stats[k] is None for k in dashboards.TIMING_KEYS)
    assert "bookings" in body["period"]
