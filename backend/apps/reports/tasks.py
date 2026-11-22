import time

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.bookings.models import Booking
from apps.core import events
from apps.media import storage

from . import context, definition, render
from .models import PdfTemplateVersion, Report

MAX_RETRIES = 2


def published_template(booking: Booking, insp) -> PdfTemplateVersion | None:
    return (PdfTemplateVersion.objects.filter(template__form=insp.form_version.form,
                                              status="published").order_by("-number").first())


def build_pdf(booking: Booking, insp, tv: PdfTemplateVersion, token: str, revision: int):
    """(pdf bytes, filename). Used by the real render and by template previews."""
    blocks = context.build(booking, insp, tv.definition)
    stamp = timezone.localtime().strftime("%d-%m-%Y %H:%M")
    html_text = render.render_html(blocks, tv.definition, booking_id=booking.booking_id,
                                   revision=revision, stamp=stamp, token=token)
    name = definition.filename_for(tv.definition, booking.booking_id,
                                   timezone.localdate().strftime("%d-%m-%Y"))
    return render.render_pdf(html_text), name


def _render_with_retries(booking, insp, tv, token: str, revision: int):
    """First try plus two retries; raises the last error if all fail."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            pdf, name = build_pdf(booking, insp, tv, token, revision)
            key = f"reports/{booking.id}/rev{revision}.pdf"
            storage.put(key, pdf, "application/pdf")
            return pdf, name, key
        except Exception:  # noqa: BLE001
            if attempt == MAX_RETRIES:
                raise
            time.sleep(settings.PDF_RETRY_DELAY)
    raise AssertionError("unreachable")  # pragma: no cover


@shared_task(soft_time_limit=120, time_limit=150)
def render_report(booking_id: str) -> str:
    """Make (or remake) the PDF of a completed booking. Latest revision only is kept."""
    booking = Booking.objects.get(pk=booking_id)
    insp = context.latest_inspection(booking)
    tv = published_template(booking, insp) if insp else None
    if insp is None or tv is None:
        return "skipped"                          # nothing to render yet
    report, _ = Report.objects.get_or_create(booking=booking)
    revision = report.revision + 1
    try:
        pdf, name, key = _render_with_retries(booking, insp, tv, report.token, revision)
    except Exception as exc:  # noqa: BLE001 - recorded, not raised: Ops see it as a problem
        Report.objects.filter(pk=report.pk).update(status="failed", error=str(exc)[:500])
        events.emit("alert.pdf_failed", booking=str(booking.id), error=str(exc)[:200])
        return "failed"
    with transaction.atomic():
        report = Report.objects.select_for_update().get(pk=report.pk)
        old = report.key
        report.revision, report.key, report.filename = revision, key, name
        report.status, report.stale, report.error = "ready", False, ""
        report.template_version, report.generated_at = tv, timezone.now()
        report.save()
    if old:
        storage.delete(old)
    events.emit("pdf.ready", booking=str(booking.id), booking_id=booking.booking_id,
                revision=revision)
    return "ready"
