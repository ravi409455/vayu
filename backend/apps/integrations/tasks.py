"""Celery jobs that send webhook deliveries and retry the ones that are due."""
from datetime import timedelta

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

from . import webhooks
from .models import Delivery

STUCK_SENDING = timedelta(minutes=10)    # a worker that died mid-send


def claim(delivery_id: str) -> Delivery | None:
    """Take a delivery for sending; None if another worker has it or it is finished."""
    n = Delivery.objects.filter(pk=delivery_id, status__in=("pending", "retrying")).update(
        status="sending", last_attempt_at=timezone.now())
    return Delivery.objects.select_related("integration").get(pk=delivery_id) if n else None


@shared_task(soft_time_limit=60, time_limit=90)
def deliver(delivery_id: str) -> str:
    d = claim(delivery_id)
    if d is None:
        return "skipped"
    return webhooks.attempt(d).status


@shared_task
def retry_due() -> int:
    """Run every minute by Celery beat: send what is due again."""
    now = timezone.now()
    due = Delivery.objects.filter(
        Q(status="retrying", next_retry_at__lte=now)
        | Q(status="sending", last_attempt_at__lt=now - STUCK_SENDING)).values_list("id", flat=True)
    ids = [str(i) for i in due]
    for i in ids:
        Delivery.objects.filter(pk=i, status="sending").update(status="retrying")
        deliver.delay(i)
    return len(ids)
