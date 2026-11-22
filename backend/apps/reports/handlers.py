"""Reacts to domain events: render when a booking completes, flag the PDF stale on edits."""
from .models import Report


def on_event(name: str, payload: dict) -> None:
    if name == "inspection.completed":
        from .tasks import render_report

        render_report.delay(payload["booking"])
    elif name in ("inspection.updated", "media.deleted"):
        Report.objects.filter(booking_id=payload["booking"]).update(stale=True)
