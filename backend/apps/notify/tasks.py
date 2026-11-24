from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from . import push as fcm
from .models import Notification

KEEP_DAYS = 30


@shared_task
def push(ids: list[int]) -> int:
    """Send each new bell row to its person's signed-in phone (one phone per person)."""
    from apps.accounts.models import Device

    if fcm.credential() is None:
        return 0
    sent = 0
    for n in Notification.objects.filter(pk__in=ids).select_related("booking"):
        for d in Device.objects.filter(user_id=n.user_id, revoked_at__isnull=True).exclude(
                push_token=""):
            data = {"id": str(n.id), "kind": n.kind, "title": n.title, "body": n.body,
                    "booking": str(n.booking_id or "")}
            if fcm.send(d.push_token, data):
                sent += 1
            else:
                Device.objects.filter(pk=d.pk).update(push_token="")
    return sent


@shared_task
def late_starts() -> int:
    """Every 5 min: jobs past their time by more than the Settings late-start limit and not
    started → Ops hear once per job. Also drops bell rows older than 30 days."""
    from apps.bookings import timing
    from apps.bookings.models import Booking

    from .handlers import to_ops

    now = timezone.now()
    Notification.objects.filter(created_at__lt=now - timedelta(days=KEEP_DAYS)).delete()
    grace = timedelta(minutes=timing.config()["late_grace_minutes"])
    told = Notification.objects.filter(kind="late").values("booking_id")
    today = timezone.localdate(now)
    count = 0
    # ponytail: a rescheduled job that was already reported late isn't reported again
    for b in Booking.objects.filter(stage__in=("draft", "assigned"), started_at__isnull=True,
                                    inspection_date__range=(today - timedelta(days=1), today)
                                    ).exclude(pk__in=told):
        booked = timing.slot(b)
        if booked is None or now <= booked + grace:
            continue
        mins = round((now - booked).total_seconds() / 60)
        to_ops(b, "late", f"{b.booking_id} not started",
               f"{mins} min past {b.answers.get('inspection_time')}")
        count += 1
    return count
