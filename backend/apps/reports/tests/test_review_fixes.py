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
    # the PDF made at completion stays the customer's (H-18); the failure is kept beside it
    assert r.status == "ready" and r.key and r.error == "timeout" and r.render_started_at is None
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
    url = f"https://vayu.carcid.in/report/verify/{token}"
    values = {"sys": {"booking_id": "SA1", "inspection_type": "PDI", "verify_url": url}}
    pages = [{"title": "V", "parts": [{"type": "verify"}]}]
    pdf = render.render_pdf(render.render_html(pages, {}, values))
    text = pypdf.PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    assert f"vayu.carcid.in/report/verify/{token}" in text


def test_the_report_info_carries_the_public_verify_link(report_env, settings):
    from apps.reports.models import Report

    env, b = report_env
    got = env.ops.get(f"/api/v1/bookings/{b['id']}/report").json()
    token = Report.objects.get(booking_id=b["id"]).token
    assert got["verify_url"] == f"{settings.VERIFY_BASE_URL}/{token}"


# ---------------------------------------------------------------- the benchmark command

def test_the_pdf_benchmark_renders_cleans_up_and_reports(renv):
    from io import StringIO

    from django.core.management import call_command

    from apps.bookings.models import Booking
    from apps.media import storage
    from apps.media.models import MediaAsset

    out = StringIO()
    call_command("bench_pdf", photos=3, form="pdi", field="photo_a", stdout=out)
    assert "3 photos ->" in out.getvalue() and "PASS" in out.getvalue()
    assert not Booking.objects.filter(booking_id__startswith="BENCH").exists()      # rolled back
    assert not MediaAsset.objects.exists()
    assert not storage.exists("bench/x")
    from django.core.management.base import CommandError

    with pytest.raises(CommandError, match="Only 0 of 2 photos"):        # F-082: no false PASS
        call_command("bench_pdf", photos=2, form="pdi", field="door_photo", stdout=StringIO())


def test_the_pdf_benchmark_needs_a_published_form_and_a_user(db):
    from django.core.management import call_command
    from django.core.management.base import CommandError

    with pytest.raises(CommandError, match="published inspection form"):
        call_command("bench_pdf", photos=1, form="nope")


def test_the_pdf_benchmark_needs_someone_to_own_the_data(renv):
    from unittest import mock

    from django.core.management import call_command
    from django.core.management.base import CommandError

    nobody = mock.MagicMock()
    nobody.objects.filter.return_value.first.return_value = None
    nobody.objects.first.return_value = None
    with mock.patch("apps.reports.management.commands.bench_pdf.User", nobody), \
            pytest.raises(CommandError, match="no users"):
        call_command("bench_pdf", photos=1, form="pdi", field="photo_a")


def test_the_slow_verdict_is_reported(renv, monkeypatch):
    from io import StringIO

    from django.core.management import call_command

    from apps.reports.management.commands import bench_pdf

    monkeypatch.setattr(bench_pdf, "LIMIT_SECONDS", -1)
    out = StringIO()
    call_command("bench_pdf", photos=1, form="pdi", field="photo_a", stdout=out)
    assert "TOO SLOW" in out.getvalue()


# ---------------------------------------------------------------- discarding a template draft

def test_a_template_draft_can_be_discarded_but_never_the_first_unpublished_one(renv):
    from apps.accounts.models import AuditLog
    from apps.reports.models import PdfTemplateVersion
    from apps.reports.tests.test_reports import set_template

    admin = renv.admin
    first = renv.template_version_id
    r = admin.delete(f"/api/v1/pdf-template-versions/{first}")
    assert r.status_code == 409 and r.json()["code"] == "FIRST_DRAFT"       # never published
    set_template(renv)                                                    # v1 published
    r = admin.delete(f"/api/v1/pdf-template-versions/{first}")
    assert r.status_code == 409 and r.json()["code"] == "NOT_A_DRAFT"
    draft = admin.post(f"/api/v1/pdf-templates/{renv.template_id}/drafts").json()
    assert admin.delete(f"/api/v1/pdf-template-versions/{draft['id']}").status_code == 204
    assert not PdfTemplateVersion.objects.filter(pk=draft["id"]).exists()
    assert PdfTemplateVersion.objects.filter(pk=first, status="published").exists()
    assert AuditLog.objects.filter(action="pdf_template.draft_discard").exists()
    assert renv.ops.delete(f"/api/v1/pdf-template-versions/{first}").status_code == 403


def test_a_role_left_off_a_forms_submission_list_cannot_open_its_reports(report_env):
    env, b = report_env
    url = f"/api/v1/bookings/{b['id']}/report"
    assert env.ops.get(url).status_code == 200
    env.admin.patch(f"/api/v1/forms/{env.form_id}", {"submission_roles": ["expert"]},
                    format="json")
    assert env.ops.get(url).status_code == 404
    assert env.ops.get("/api/v1/problems/reports").status_code == 200
    assert env.admin.get(url).status_code == 200


def test_a_switched_off_form_still_hides_its_reports(report_env):
    from apps.forms.models import Form

    env, b = report_env
    url = f"/api/v1/bookings/{b['id']}/report"
    env.admin.patch(f"/api/v1/forms/{env.form_id}", {"submission_roles": ["expert"]},
                    format="json")
    Form.objects.filter(pk=env.form_id).update(is_active=False)
    assert env.ops.get(url).status_code == 404
    assert env.admin.get(url).status_code == 200


def test_the_newest_layout_is_checked_against_the_form_as_it_is_now(renv):
    from apps.forms.models import Form
    from apps.reports.models import PdfTemplate, PdfTemplateVersion
    from apps.reports.service import latest_layout_issues
    from apps.reports.tests.test_reports import set_template

    form = Form.objects.get(pk=renv.form_id)
    assert latest_layout_issues(form) == []                                  # no template at all
    set_template(renv)
    assert latest_layout_issues(form) == []                                  # the layout fits
    PdfTemplateVersion.objects.create(
        template=PdfTemplate.objects.get(form=form), number=99, definition={
            "schema": 2, "pages": [{"title": "T", "parts": [{"type": "table", "source": {
                "kind": "fields", "rows": [{"field": "inspection.nope"}]}}]}]})
    issues = latest_layout_issues(form)
    assert [i["code"] for i in issues] == ["UNKNOWN_FIELD"] and "nope" in issues[0]["message"]
