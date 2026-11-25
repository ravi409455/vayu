"""F-089 / F-090: Admin lists and the external API cost the same queries for 2 or 6 rows."""
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.bookings.tests.conftest import create, custom_form, publish_draft
from apps.bookings.tests.test_submissions import assign, ienv, start, submit  # noqa: F401

from .conftest import make
from .test_apikeys import client, new_key

pytestmark = pytest.mark.django_db


def _queries(c, url) -> int:
    with CaptureQueriesContext(connection) as ctx:
        r = c.get(url)
    assert r.status_code == 200, r.content
    return len(ctx)


def _grows(c, url, add, n_few=2, n_more=4) -> tuple[int, int]:
    for i in range(n_few):
        add(i)
    few = _queries(c, url)
    for i in range(n_few, n_few + n_more):
        add(i)
    return few, _queries(c, url)


def test_the_integrations_list(ienv):
    few, many = _grows(ienv.admin, "/api/v1/integrations",
                       lambda i: make(ienv, ienv.form_id, event="booking.updated"))
    assert many <= few, (few, many)


def test_the_forms_list(ienv):
    def add(i):
        f = custom_form(ienv.admin, f"f{i}", f"F{i}")
        publish_draft(ienv.admin, f["id"])
    few, many = _grows(ienv.admin, "/api/v1/forms", add)
    assert many <= few, (few, many)


def test_the_library_list(ienv):
    def add(i):
        assert ienv.admin.post("/api/v1/library", {"kind": "field", "key": f"k{i}", "name": "K",
                               "definition": {"key": f"k{i}", "label": "K",
                                              "type": "short_text"}},
                               format="json").status_code == 201
    few, many = _grows(ienv.admin, "/api/v1/library", add)
    assert many <= few, (few, many)


def test_the_external_bookings_list(ienv):
    c = client(new_key(ienv))
    few, many = _grows(c, "/api/v1/ext/bookings",
                       lambda i: create(ienv.ops, booking_id=f"X{i}"))
    assert many <= few, (few, many)


def test_a_bookings_inspections(ienv):
    from apps.bookings.models import Inspection

    b = create(ienv.ops, booking_id="I1").json()
    assign(ienv, b)
    start(ienv.expert, b)
    submit(ienv.expert, b)
    url = f"/api/v1/bookings/{b['id']}/inspections"
    one = _queries(ienv.ops, url)
    insp = Inspection.objects.get(booking_id=b["id"])
    for _ in range(3):                                   # set-aside copies (conflicts)
        insp.pk, insp.client_start_uuid, insp.client_submission_uuid = None, None, None
        insp.status = "superseded"
        insp.save()
    assert _queries(ienv.ops, url) <= one                # levels once, not per inspection
