"""F-247: every try at making a PDF is kept (the Report row only holds the latest state)."""
from unittest import mock

import pytest

from apps.reports import tasks
from apps.reports.models import Report, ReportRender

from .test_report_rules import done  # noqa: F401
from .test_reports import renv  # noqa: F401

pytestmark = pytest.mark.django_db


def test_each_render_try_is_kept_with_its_outcome(done, logged, caplog):
    env, b, r = done
    first = ReportRender.objects.get(report=r)
    assert (first.revision, first.ok, first.error) == (1, True, "")
    assert first.started_at <= first.finished_at
    with mock.patch.object(tasks, "_render_with_retries", side_effect=RuntimeError("boom")):
        assert tasks.render_report(b["id"]) == "failed"
    assert tasks.render_report(b["id"]) == "ready"
    rows = list(ReportRender.objects.filter(report=r).order_by("id").values_list("revision", "ok", "error"))
    assert rows == [(1, True, ""), (2, False, "render_failed"), (2, True, "")]
    assert Report.objects.get(pk=r.pk).revision == 2          # the report itself keeps the latest only
    assert [x["revision"] for x in logged("pdf.render_started")] == [2, 2]
    [failed] = [x for x in caplog.records if getattr(x, "event", "") == "pdf.render_failed"]
    assert failed.reason == "render_failed"
    finished = logged("pdf.render_done")[-1]
    assert finished["pages"] >= 1 and finished["duration_ms"] >= 0
