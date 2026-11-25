"""Plan batch 6 (H-12 / F-079 / R-22): the main lists cost a fixed number of queries, however many
rows they hold."""
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.bookings.tests.test_submissions import assign, ienv, start  # noqa: F401

from .conftest import create

pytestmark = pytest.mark.django_db


def _queries(client, url, **params) -> int:
    with CaptureQueriesContext(connection) as ctx:
        r = client.get(url, params)
    assert r.status_code == 200, r.content
    return len(ctx)


def _jobs(env, n, prefix):
    for i in range(n):
        b = create(env.ops, booking_id=f"{prefix}{i}").json()
        assign(env, b)
        if i % 2:
            start(env.expert, b)
        env.ops.post(f"/api/v1/bookings/{b['id']}/reschedule",
                     {"date": "2026-10-20", "time": "11:00", "reason": "customer_request"},
                     format="json")


@pytest.mark.parametrize("who,url,params", [
    ("expert", "/api/v1/sync/jobs", {"since": "2026-01-01T00:00:00Z"}),
    ("ops", "/api/v1/bookings", {}),
    ("expert", "/api/v1/bookings", {}),
    ("ops", "/api/v1/bookings/count", {}),
    ("ops", "/api/v1/problems/stuck-uploads", {}),
])
def test_a_list_costs_the_same_queries_for_3_or_12_rows(ienv, who, url, params):
    client = getattr(ienv, who)
    _jobs(ienv, 3, "Q")
    few = _queries(client, url, **params)
    _jobs(ienv, 9, "R")
    many = _queries(client, url, **params)
    assert many <= few, f"{url}: {few} queries for 3 rows, {many} for 12"
