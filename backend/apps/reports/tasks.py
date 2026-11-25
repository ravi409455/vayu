import logging
import time
from datetime import timedelta

from botocore.exceptions import ClientError
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.bookings.models import Booking
from apps.core import events
from apps.media import storage

from . import context, definition, render, shared
from .models import PdfTemplateVersion, Report, mark_out_of_date

MAX_RETRIES = 2
SOFT_LIMIT, HARD_LIMIT = 300, 330        # seconds: 150 photos must fit with room to spare
STUCK_AFTER = timedelta(seconds=HARD_LIMIT + 60)   # a render older than this was killed
RETRY_FAILED = timedelta(minutes=30)               # a failed render is tried again after this
logger = logging.getLogger(__name__)


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


def preview(booking: Booking, insp, definition_: dict, edge: int = 480):
    """(pdf bytes, filename, layout, checks) of any definition for one booking: nothing is
    stored."""
    definition_ = shared.resolve(definition_)
    src = context.Source(booking, insp, revision=0, token="preview")
    pages = context.build(src, definition_)
    values = src.values()
    pdf, layout, checks = render.render_with_layout(render.render_html(pages, definition_, values,
                                                               edge=edge))
    return pdf, definition.filename_for(definition_, values), layout, checks


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
            if attempt == MAX_RETRIES:
                raise
            time.sleep(settings.PDF_RETRY_DELAY)
    raise AssertionError("unreachable")  # pragma: no cover


def _finds(booking: Booking):
    insp = booking.counted_inspection()
    return insp, (published_template(booking, insp) if insp else None)


@shared_task(soft_time_limit=SOFT_LIMIT, time_limit=HARD_LIMIT)
def render_report(booking_id: str) -> str:
    """Make the PDF of a completed booking: once by itself when it completes, then each time Ops
    press Regenerate. Latest revision only is kept."""
    booking = Booking.objects.get(pk=booking_id)
    insp, tv = _finds(booking)
    if insp is None or tv is None:
        return "skipped"                          # nothing to render yet
    report, _ = Report.objects.get_or_create(booking=booking)
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
    try:
        pdf, name, key = _render_with_retries(booking, insp, tv, report.token, revision)
    except Exception as exc:  # noqa: BLE001 - recorded, not raised: Ops see it as a problem
        reason = ("timeout" if isinstance(exc, SoftTimeLimitExceeded)
                  else "storage_failed" if isinstance(exc, ClientError) else "render_failed")
        logger.exception("PDF render failed for booking %s", booking.id)   # detail stays in logs
        # a PDF already made stays ready (the customer's QR keeps working, H-18); the failure is
        # kept beside it for Ops
        # the last PDF no longer shows the data that asked for a new one: out of date again
        Report.objects.filter(pk=report.pk).update(status="ready" if report.key else "failed",
                                                   error=reason, render_started_at=None,
                                                   retry_at=timezone.now() + RETRY_FAILED)
        if report.key:
            mark_out_of_date(Report.objects.filter(pk=report.pk))
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
    if old:
        storage.delete(old)
    events.emit("pdf.ready", booking=str(booking.id), booking_id=booking.booking_id,
                revision=revision)
    return "ready"


@shared_task
def sweep_reports() -> int:
    """Every few minutes: try again the renders that failed a while ago or whose worker was
    killed. Never a report that is only out of date: Ops regenerate those."""
    now = timezone.now()
    due = Report.objects.filter(booking__stage="completed").filter(
        Q(render_started_at__lt=now - STUCK_AFTER) | Q(retry_at__lte=now))
    ids = [str(b) for b in due.values_list("booking_id", flat=True)]
    for b in ids:
        render_report.delay(b)
    return len(ids)
