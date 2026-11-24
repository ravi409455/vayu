"""Reacts to domain events. The report is never made by hand: it is made when a booking
completes and made again whenever anything it shows changes afterwards (answers, photos, Key
Checks, ratings, booking details)."""
from apps.core import tasks as core_tasks

from .models import Report

CHANGES = ("inspection.updated", "media.deleted", "booking.updated")


def on_event(name: str, payload: dict) -> None:
    if name != "inspection.completed" and name not in CHANGES:
        return
    from apps.bookings.models import Booking

    from .tasks import render_report

    booking = payload["booking"]
    # marked first: a render already running sees the mark and runs once more when it ends
    Report.objects.filter(booking_id=booking).update(stale=True)
    if name == "inspection.completed" or Booking.objects.filter(pk=booking,
                                                                 stage="completed").exists():
        # the change is saved with its transaction: the worker must read it after the commit
        core_tasks.after_commit(lambda: render_report.delay(booking))
