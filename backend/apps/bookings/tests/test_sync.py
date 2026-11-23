"""What an expert's phone downloads to work offline (GET sync/jobs)."""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.bookings.models import Booking
from apps.bookings.tests.test_submissions import assign, ienv, start  # noqa: F401
from apps.forms.models import MasterListItem

from .conftest import create

pytestmark = pytest.mark.django_db


def sync(client, **query):
    return client.get("/api/v1/sync/jobs", query)


def test_an_expert_gets_their_jobs_with_the_forms_and_lists_to_work_offline(ienv, booking):
    assign(ienv, booking)
    r = sync(ienv.expert)
    assert r.status_code == 200, r.json()
    body = r.json()
    assert body["server_time"] and body["changes"] == []
    (job,) = body["jobs"]
    assert job["id"] == booking["id"] and job["assigned_to_me"] is True and job["my_draft"] is None
    version = str(job["versions"]["inspection"])
    tree = body["forms"][version]
    assert "rating_config" not in tree                                   # experts never see it
    assert any(f["key"] == "door" for p in tree["pages"] for s in p["sections"] for f in s["fields"])
    assert {"key": "delhi", "label": "Delhi"} in body["lists"]["city"]


def test_forms_the_phone_already_has_are_not_sent_again(ienv, booking):
    assign(ienv, booking)
    first = sync(ienv.expert).json()
    have = ",".join(first["forms"])
    again = sync(ienv.expert, have=have).json()
    assert again["forms"] == {} and again["jobs"][0]["versions"] == first["jobs"][0]["versions"]


def test_archived_list_items_are_left_out(ienv, booking):
    MasterListItem.objects.filter(key="delhi").update(archived=True)
    assign(ienv, booking)
    assert {"key": "delhi", "label": "Delhi"} not in sync(ienv.expert).json()["lists"]["city"]


def test_only_my_jobs_and_only_recent_finished_ones(ienv):
    mine = create(ienv.ops, booking_id="S1").json()
    other = create(ienv.ops, booking_id="S2").json()
    old = create(ienv.ops, booking_id="S3").json()
    assign(ienv, mine)
    assign(ienv, other, ienv.make_user("expert", username="e5"))
    assign(ienv, old)
    Booking.objects.filter(pk=old["id"]).update(
        stage="completed", inspection_date=timezone.localdate() - timedelta(days=8))
    ids = {j["id"] for j in sync(ienv.expert).json()["jobs"]}
    assert ids == {mine["id"]}


def test_a_job_taken_away_while_i_hold_a_draft_stays_with_my_draft(ienv, booking):
    assign(ienv, booking)
    started = start(ienv.expert, booking).json()
    ienv.ops.post(f"/api/v1/bookings/{booking['id']}/force-release")
    assign(ienv, booking, ienv.make_user("expert", username="e6"))
    (job,) = sync(ienv.expert).json()["jobs"]
    assert job["assigned_to_me"] is False and job["my_draft"] == started["inspection"]["id"]


def test_a_job_whose_form_is_missing_is_listed_without_forms(ienv, booking):
    assign(ienv, booking)
    Booking.objects.filter(pk=booking["id"]).update(inspection_type="gone")
    (job,) = sync(ienv.expert).json()["jobs"]
    assert job["versions"] == {}


def test_what_ops_changed_since_the_last_sync(ienv, booking):
    assign(ienv, booking)
    since = timezone.now().isoformat()
    ienv.ops.post(f"/api/v1/bookings/{booking['id']}/reschedule",
                  {"date": "2026-10-20", "time": "11:00", "reason": "customer_request"},
                  format="json")
    changes = sync(ienv.expert, since=since).json()["changes"]
    assert changes and changes[0]["booking"] == booking["id"]
    assert changes[0]["booking_id"] == booking["booking_id"] and changes[0]["by"]
    assert sync(ienv.expert).json()["changes"] == []                     # no "since": nothing


def test_changes_hide_fields_the_expert_may_not_see(ienv, booking):
    from apps.bookings import activity
    from apps.bookings.models import Booking as B
    from apps.forms.models import Field

    assign(ienv, booking)
    since = timezone.now().isoformat()
    Field.objects.filter(key="customer_phone", version__form__type="booking").update(
        access={"expert": {"assigned": "hidden"}})
    activity.log(B.objects.get(pk=booking["id"]), ienv.ops_user, "edited",
                 keys=["customer_phone", "address"])
    (change,) = sync(ienv.expert, since=since).json()["changes"]
    assert change["keys"] == ["address"]                                 # the hidden one is gone


@pytest.mark.parametrize("query", [{"since": "yesterday"}, {"have": "1,x"}])
def test_bad_query_values_are_refused(ienv, query):
    r = sync(ienv.expert, **query)
    assert r.status_code == 400 and r.json()["code"] == "INVALID_QUERY"
