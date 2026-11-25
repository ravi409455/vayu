"""Reacts to domain events. A booking's report is made by itself once, when the booking
completes. After that nothing makes it again by itself: any change it shows (answers, files,
Key Checks, ratings, booking details) only marks it out of date, and Ops press Regenerate."""
from apps.core import tasks as core_tasks

from .models import Report, mark_out_of_date

CHANGES = ("inspection.updated", "media.deleted", "booking.updated")


def on_event(name: str, payload: dict) -> None:
    if name in CHANGES:
        mark_out_of_date(Report.objects.filter(booking_id=payload["booking"]))
    elif name == "inspection.completed":
        from .tasks import render_report

        booking = payload["booking"]
        # the change is saved with its transaction: the worker must read it after the commit
        core_tasks.after_commit(lambda: render_report.delay(booking))
