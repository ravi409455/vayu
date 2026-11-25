"""F-159: regression tests for risky paths the review found untested (no behaviour change)."""
import pytest
from rest_framework.test import APIClient

from apps.bookings.models import Booking, Inspection
from apps.reports.models import Report

from .test_report_rules import _late_submit, done  # noqa: F401
from .test_reports import renv  # noqa: F401

pytestmark = pytest.mark.django_db


def test_the_customers_photo_link_follows_the_inspection_ops_keep(done, settings):
    """During a conflict the link shows the counted (first) inspection's photos; once Ops keep the
    late one, it shows that one's (here none), never the set-aside inspection's files."""
    env, b, r = done
    _late_submit(env, b, settings)                     # the late inspection has no photos
    assert Booking.objects.get(pk=b["id"]).conflict == "TWO_EXPERTS"
    assert APIClient().get(f"/api/v1/verify/{r.token}/photos").json()["count"] == 3
    late = Inspection.objects.get(booking_id=b["id"], expert=env.expert_user)
    assert env.ops.post(f"/api/v1/bookings/{b['id']}/resolve-conflict",
                        {"inspection": str(late.id)}, format="json").status_code == 200
    token = Report.objects.get(booking_id=b["id"]).token
    gone = APIClient().get(f"/api/v1/verify/{token}/photos")
    assert gone.status_code == 404 and gone.json()["code"] == "NO_MEDIA"
