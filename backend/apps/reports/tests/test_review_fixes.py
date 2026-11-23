"""Review fixes for PDF rendering: one render at a time, killed/timed-out renders, edits mid-render."""
from unittest import mock

import pytest

from apps.reports.models import Report
from apps.reports.tests.test_reports import renv  # noqa: F401

pytestmark = pytest.mark.django_db


# ---------------------------------------------------- PDF: one render at a time, limits

@pytest.fixture
def report_env(renv, settings):
    from apps.reports.tests.test_reports import complete_job, set_template

    set_template(renv)
    return renv, complete_job(renv, settings=settings)


def test_a_second_render_while_one_runs_is_dropped(report_env):
    from django.utils import timezone

    from apps.reports import tasks

    env, b = report_env
    r = Report.objects.get(booking_id=b["id"])
    revision = r.revision
    Report.objects.filter(pk=r.pk).update(render_started_at=timezone.now())
    assert tasks.render_report(b["id"]) == "busy"
    assert Report.objects.get(pk=r.pk).revision == revision


def test_a_killed_render_is_retried_later_and_listed_as_a_problem(report_env):
    from django.utils import timezone

    from apps.reports import tasks

    env, b = report_env
    r = Report.objects.get(booking_id=b["id"])
    Report.objects.filter(pk=r.pk).update(
        render_started_at=timezone.now() - tasks.STUCK_AFTER - tasks.timedelta(seconds=5))
    assert [p["booking"] for p in env.ops.get("/api/v1/problems/reports").json()] == [b["id"]]
    assert tasks.render_report(b["id"]) == "ready"           # the stale claim can be taken over
    assert Report.objects.get(pk=r.pk).render_started_at is None
    assert env.ops.get("/api/v1/problems/reports").json() == []


def test_a_timeout_is_recorded_and_not_retried(report_env):
    from celery.exceptions import SoftTimeLimitExceeded

    from apps.reports import tasks

    env, b = report_env
    with mock.patch("apps.reports.tasks.build_pdf", side_effect=SoftTimeLimitExceeded()) as m:
        assert tasks.render_report(b["id"]) == "failed"
    assert m.call_count == 1
    r = Report.objects.get(booking_id=b["id"])
    assert r.status == "failed" and r.error == "timeout" and r.render_started_at is None
    assert tasks.SOFT_LIMIT >= 300 and tasks.HARD_LIMIT > tasks.SOFT_LIMIT


def test_an_edit_during_a_render_keeps_the_pdf_marked_stale(report_env):
    from apps.reports import tasks

    env, b = report_env
    real = tasks.build_pdf

    def edit_then_build(*a, **k):                                   # an edit lands mid-render
        from apps.reports.handlers import on_event

        on_event("inspection.updated", {"booking": b["id"]})
        return real(*a, **k)

    with mock.patch("apps.reports.tasks.build_pdf", side_effect=edit_then_build):
        assert tasks.render_report(b["id"]) == "ready"
    assert Report.objects.get(booking_id=b["id"]).stale is True


def test_the_verify_link_never_wraps_even_with_hyphens_in_the_token():
    """The verify link stays on one line even when the token has hyphens (breakable characters)."""
    import io

    import pypdf

    from apps.reports import render

    token = "-".join(["abcdefgh"] * 4)                        # 35 characters, four hyphens
    pdf = render.render_pdf(render.render_html([], {}, booking_id="SA1", revision=1,
                                               stamp="now", token=token))
    text = pypdf.PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    assert f"verify.carcid.in/{token}" in text


def test_the_report_info_carries_the_public_verify_link(report_env, settings):
    from apps.reports.models import Report

    env, b = report_env
    got = env.ops.get(f"/api/v1/bookings/{b['id']}/report").json()
    token = Report.objects.get(booking_id=b["id"]).token
    assert got["verify_url"] == f"{settings.VERIFY_BASE_URL}/{token}"
