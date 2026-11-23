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

from . import context, definition, render
from .models import PdfTemplateVersion, Report

MAX_RETRIES = 2
SOFT_LIMIT, HARD_LIMIT = 300, 330        # seconds: 150 photos must fit with room to spare
STUCK_AFTER = timedelta(seconds=HARD_LIMIT + 60)   # a render older than this was killed
logger = logging.getLogger(__name__)


def published_template(booking: Booking, insp) -> PdfTemplateVersion | None:
    return (PdfTemplateVersion.objects.filter(template__form=insp.form_version.form,
                                              status="published").order_by("-number").first())


def build_pdf(booking: Booking, insp, tv: PdfTemplateVersion, token: str, revision: int,
              edge: int = render.PRINT_EDGE):
    """(pdf bytes, filename). Used by the real render and by template previews (small photos)."""
    src = context.Source(booking, insp, revision=revision, token=token)
    pages = context.build(src, tv.definition)
    values = src.values()
    html_text = render.render_html(pages, tv.definition, values, edge=edge)
    return render.render_pdf(html_text), definition.filename_for(tv.definition, values)


def preview(booking: Booking, insp, definition_: dict, edge: int = 480):
    """(pdf bytes, filename, layout) of any definition for one booking: nothing is stored."""
    src = context.Source(booking, insp, revision=0, token="preview")
    pages = context.build(src, definition_)
    values = src.values()
    pdf, layout = render.render_with_layout(render.render_html(pages, definition_, values,
                                                               edge=edge))
    return pdf, definition.filename_for(definition_, values), layout


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


@shared_task(soft_time_limit=SOFT_LIMIT, time_limit=HARD_LIMIT)
def render_report(booking_id: str) -> str:
    """Make (or remake) the PDF of a completed booking. Latest revision only is kept."""
    booking = Booking.objects.get(pk=booking_id)
    insp = context.latest_inspection(booking)
    tv = published_template(booking, insp) if insp else None
    if insp is None or tv is None:
        return "skipped"                          # nothing to render yet
    report, _ = Report.objects.get_or_create(booking=booking)
    now = timezone.now()
    # one render at a time per booking: a second request while one runs is dropped (edits made
    # meanwhile set 'stale', and the claim below clears it only for data read after this point)
    claimed = Report.objects.filter(pk=report.pk).filter(
        Q(render_started_at__isnull=True) | Q(render_started_at__lt=now - STUCK_AFTER)
    ).update(render_started_at=now, stale=False)
    if not claimed:
        return "busy"
    report.refresh_from_db()
    revision = report.revision + 1
    try:
        pdf, name, key = _render_with_retries(booking, insp, tv, report.token, revision)
    except Exception as exc:  # noqa: BLE001 - recorded, not raised: Ops see it as a problem
        reason = ("timeout" if isinstance(exc, SoftTimeLimitExceeded)
                  else "storage_failed" if isinstance(exc, ClientError) else "render_failed")
        logger.exception("PDF render failed for booking %s", booking.id)   # detail stays in logs
        Report.objects.filter(pk=report.pk).update(status="failed", error=reason,
                                                   render_started_at=None)
        events.emit("alert.pdf_failed", booking=str(booking.id), reason=reason)
        return "failed"
    with transaction.atomic():
        report = Report.objects.select_for_update().get(pk=report.pk)
        old = report.key
        report.revision, report.key, report.filename = revision, key, name
        report.status, report.error, report.render_started_at = "ready", "", None
        report.template_version, report.generated_at = tv, timezone.now()
        report.save(update_fields=["revision", "key", "filename", "status", "error",
                                   "render_started_at", "template_version", "generated_at"])
    if old:
        storage.delete(old)
    events.emit("pdf.ready", booking=str(booking.id), booking_id=booking.booking_id,
                revision=revision)
    return "ready"
