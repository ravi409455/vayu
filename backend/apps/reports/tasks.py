"""Celery jobs that render a booking's PDF report (with retries) and sweep failed renders."""
import contextlib
import logging
import re
import time
import zlib
from datetime import timedelta

from botocore.exceptions import ClientError
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.bookings.models import Booking
from apps.core import events, log
from apps.media import storage

from . import context, definition, render, shared
from .models import PdfTemplateVersion, Report, ReportRender, mark_out_of_date

MAX_RETRIES = 2
SOFT_LIMIT, HARD_LIMIT = 300, 330        # seconds: 150 photos must fit with room to spare
STUCK_AFTER = timedelta(seconds=HARD_LIMIT + 60)   # a render older than this was killed
RETRY_FAILED = timedelta(minutes=30)               # a failed render is tried again after this
MISSING_AFTER = timedelta(minutes=10)    # a completed booking with no report by now lost its render
MISSING_FOR = timedelta(days=2)          # the sweep stops trying; Ops still see it in Problems
logger = logging.getLogger(__name__)
STREAM = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.S)
PAGE_COUNT = re.compile(rb"/Type\s*/Pages\b.*?/Count\s+(\d+)", re.S)


def published_template(booking: Booking, insp) -> PdfTemplateVersion | None:
    """The layout made for the inspection's form version (F-119): the newest template version
    published before the next form version came out, so rows the older form has still print.
    An inspection on the latest form version gets the newest layout."""
    from apps.forms.models import FormVersion

    nxt = (FormVersion.objects.filter(form_id=insp.form_version.form_id, status="published",
                                      number__gt=insp.form_version.number)
           .order_by("number").values_list("published_at", flat=True).first())
    live = PdfTemplateVersion.objects.filter(template__form=insp.form_version.form,
                                             status="published")
    made_for = live.filter(published_at__lt=nxt) if nxt else live
    return (made_for.order_by("-number").first()            # pinned to an older version
            or live.order_by("number").first())             # no layout that old: the oldest


def build_pdf(booking: Booking, insp, tv: PdfTemplateVersion, token: str, revision: int,
              edge: int = render.PRINT_EDGE):
    """(pdf bytes, filename). Used by the real render and by template previews (small photos)."""
    d = shared.resolve(tv.definition)                  # the theme and shared parts it names
    src = context.Source(booking, insp, revision=revision, token=token)
    pages = context.build(src, d)
    values = src.values()
    html_text = render.render_html(pages, d, values, edge=edge)
    return render.render_pdf(html_text), definition.filename_for(d, values)


def preview(booking: Booking, insp, definition_: dict, edge: int = 480, *,
            only: int | None = None, numbering: tuple[int, int] | None = None):
    """(pdf bytes, filename, layout, checks) of any definition for one booking: nothing is
    stored. Each sheet of the layout says which template page it belongs to ("section": its
    place in the definition). only: draw that one template page (the designer's quick preview:
    about 1 s, not 4); numbering: its first page number and the report's page count, from the
    last whole draw. A page that does not show for this booking gives no sheets (pdf b"")."""
    definition_ = shared.resolve(definition_)
    src = context.Source(booking, insp, revision=0, token="preview")  # noqa: S106 - a label, not a secret
    pages = context.build(src, definition_)
    if only is not None:
        pages = [p for p in pages if p["at"] == only]
    values = src.values()
    name = definition.filename_for(definition_, values)
    if not pages:
        return b"", name, [], []
    pdf, layout, checks = render.render_with_layout(render.render_html(
        pages, definition_, values, edge=edge, numbering=numbering if only is not None else None))
    for sheet in layout:
        sheet["section"] = pages[sheet["section"]]["at"] if sheet["section"] is not None else None
    return pdf, name, layout, checks


def page_count(pdf: bytes) -> int:
    """How many pages a PDF has, for the log: the page tree's /Count, which WeasyPrint keeps in
    compressed object streams."""
    found = PAGE_COUNT.findall(pdf)
    for stream in STREAM.findall(pdf):
        with contextlib.suppress(zlib.error):          # images and fonts are not page objects
            found += PAGE_COUNT.findall(zlib.decompress(stream))
    return max((int(n) for n in found), default=0)


def _render_with_retries(booking, insp, tv, token: str, revision: int):
    """First try plus two retries; raises the last error if all fail."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            pdf, name = build_pdf(booking, insp, tv, token, revision)
            key = f"reports/{booking.id}/rev{revision}.pdf"
            storage.put(key, pdf, "application/pdf")
            return pdf, name, key
        except SoftTimeLimitExceeded:
            raise                              # out of time: retrying would only be killed
        except Exception:  # noqa: BLE001
            # tried again at once: sleeping would hold the only PDF worker and eat the time
            # limit; a lasting failure is tried again later by the sweep (F-093)
            if attempt == MAX_RETRIES:
                raise
    raise AssertionError("unreachable")  # pragma: no cover


def _finds(booking: Booking):
    insp = booking.counted_inspection()
    return insp, (published_template(booking, insp) if insp else None)


def missing_reports(since=None):
    """Completed, conflict-free bookings that have no report row although the inspection was sent
    a while ago: the first render was lost (Redis down) or skipped (no PDF layout) (H-5)."""
    now = timezone.now()
    done = {"inspections__status": "submitted",
            "inspections__submitted_at__lt": now - MISSING_AFTER}
    if since is not None:
        done["inspections__submitted_at__gt"] = since
    return Booking.objects.filter(stage="completed", conflict="", report__isnull=True,
                                  **done).distinct()


@shared_task(soft_time_limit=SOFT_LIMIT, time_limit=HARD_LIMIT)
def render_report(booking_id: str, first_only: bool = False) -> str:
    """Make the PDF of a completed booking: once by itself when it completes, then each time Ops
    press Regenerate. Latest revision only is kept. `first_only`: the sweep's catch-up of a lost
    first render, which never makes a second revision if the first one turned up meanwhile."""
    booking = Booking.objects.get(pk=booking_id)
    insp, tv = _finds(booking)
    if insp is None or tv is None:
        return "skipped"                          # nothing to render yet
    report, created = Report.objects.get_or_create(booking=booking)
    if first_only and not created:
        return "skipped"
    now = timezone.now()
    # one render at a time per booking: a second request while one runs is dropped. Claimed
    # before the data is read (F-118): a change saved after this point marks the new PDF out
    # of date again, never lost
    claimed = Report.objects.filter(pk=report.pk).filter(
        Q(render_started_at__isnull=True) | Q(render_started_at__lt=now - STUCK_AFTER)
    ).update(render_started_at=now, stale=False, stale_since=None)
    if not claimed:
        return "busy"
    report.refresh_from_db()
    booking.refresh_from_db()
    insp, tv = _finds(booking)
    if insp is None or tv is None:                # changed in between (a conflict arrived)
        Report.objects.filter(pk=report.pk).update(render_started_at=None)
        return "skipped"
    revision = report.revision + 1
    log.event("pdf.render_started", booking=str(booking.id), revision=revision)
    began = time.monotonic()
    try:
        pdf, name, key = _render_with_retries(booking, insp, tv, report.token, revision)
    except Exception as exc:  # noqa: BLE001 - recorded, not raised: Ops see it as a problem
        reason = ("timeout" if isinstance(exc, SoftTimeLimitExceeded)
                  else "storage_failed" if isinstance(exc, ClientError) else "render_failed")
        logger.exception("PDF render failed for booking %s", booking.id,   # detail stays in logs
                         extra={"event": "pdf.render_failed", "booking": str(booking.id),
                                "reason": reason})
        # a PDF already made stays ready (the customer's QR keeps working, H-18); the failure is
        # kept beside it for Ops
        # the last PDF no longer shows the data that asked for a new one: out of date again
        Report.objects.filter(pk=report.pk).update(status="ready" if report.key else "failed",
                                                   error=reason, render_started_at=None,
                                                   retry_at=timezone.now() + RETRY_FAILED)
        if report.key:
            mark_out_of_date(Report.objects.filter(pk=report.pk))
        ReportRender.objects.create(report_id=report.pk, revision=revision, started_at=now,
                                    ok=False, error=reason, template_version=tv)
        if not report.error:                         # alert once, not on every retry
            events.emit("alert.pdf_failed", booking=str(booking.id), reason=reason)
        return "failed"
    with transaction.atomic():
        report = Report.objects.select_for_update().get(pk=report.pk)
        old = report.key
        report.revision, report.key, report.filename = revision, key, name
        report.status, report.error, report.render_started_at = "ready", "", None
        report.retry_at = None
        report.template_version, report.generated_at = tv, timezone.now()
        report.first_generated_at = report.first_generated_at or report.generated_at
        report.save(update_fields=["revision", "key", "filename", "status", "error",
                                   "render_started_at", "template_version", "generated_at",
                                   "retry_at", "first_generated_at"])
        ReportRender.objects.create(report=report, revision=revision, started_at=now, ok=True,
                                    template_version=tv)
    if old:
        storage.delete(old)
    log.event("pdf.render_done", booking=str(booking.id), revision=revision,
              pages=page_count(pdf), duration_ms=round((time.monotonic() - began) * 1000))
    events.emit("pdf.ready", booking=str(booking.id), booking_id=booking.booking_id,
                revision=revision)
    return "ready"


@shared_task
def sweep_reports() -> int:
    """Every few minutes: try again the renders that failed a while ago or whose worker was
    killed, and make a first report that never came. Never a report that is only out of date:
    Ops regenerate those."""
    now = timezone.now()
    due = Report.objects.filter(booking__stage="completed").filter(
        Q(render_started_at__lt=now - STUCK_AFTER) | Q(retry_at__lte=now))
    ids = [str(b) for b in due.values_list("booking_id", flat=True)]
    for b in ids:
        render_report.delay(b)
    lost = [str(b) for b in missing_reports(since=now - MISSING_FOR).values_list("id", flat=True)]
    for b in lost:
        render_report.delay(b, first_only=True)
    return len(ids) + len(lost)
