"""Reacts to domain events: render when a booking completes, flag the PDF stale on edits."""
from apps.core import tasks as core_tasks

from .models import Report


def on_event(name: str, payload: dict) -> None:
    if name == "inspection.completed":
        from .tasks import render_report

        booking = payload["booking"]
        # submit() emits this inside its transaction: the worker must wait for the commit
        core_tasks.after_commit(lambda: render_report.delay(booking))
    elif name in ("inspection.updated", "media.deleted"):
        Report.objects.filter(booking_id=payload["booking"]).update(stale=True)
