"""Celery jobs for bookings: the check-in event (checkin.py). Both are safe to run twice."""
from celery import shared_task
from django.utils import timezone

from . import checkin
from .models import Inspection


@shared_task(soft_time_limit=30, time_limit=60)
def checkin_check(insp_id: str, arrived: bool = False) -> bool:
    return checkin.maybe_fire(insp_id, arrived=arrived)


@shared_task(soft_time_limit=30, time_limit=60)
def checkin_due() -> int:
    """Every minute: check-ins whose wait is over. Each is its own task, so one that fails (and is
    reported) never holds up the others; it is tried again the next minute."""
    due = list(Inspection.objects.filter(
        checkin_sent_at__isnull=True, checkin_due_at__lte=timezone.now())
        .order_by("checkin_due_at").values_list("pk", flat=True)[:checkin.BATCH])
    for pk in due:
        checkin_check.delay(str(pk))
    return len(due)
