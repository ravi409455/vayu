"""Q5.1: a search costs a fixed, small number of queries (field levels are cached per published
version and role)."""
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from .test_search_dashboards import many  # noqa: F401  (fixture)

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("who", ["ops", "expert"])
def test_a_search_costs_at_most_12_queries(many, who):  # noqa: F811
    client = getattr(many, who)
    client.get("/api/v1/bookings?search=asha")          # the first one fills the level cache
    with CaptureQueriesContext(connection) as ctx:
        assert client.get("/api/v1/bookings?search=asha").status_code == 200
    assert len(ctx) <= 12
