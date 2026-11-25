"""Celery jobs: push new bell rows to phones, and warn Ops about late starts."""
import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from . import push as fcm
from .models import Notification

KEEP_DAYS = 30


@shared_task
def push(ids: list[int]) -> int:
    """Wake each new bell row's person's signed-in phone. A push carries no content, only the
    row's id: the phone reads the text with its own sign-in (GET notifications returns only that
    person's rows), so a push that reaches the wrong phone reveals nothing."""
    from apps.accounts.models import Device

    if fcm.credential() is None:
        return 0
    sent = 0
    for n in Notification.objects.filter(pk__in=ids).only("id", "user_id"):
        ok = failed = 0
        for d in Device.objects.filter(user_id=n.user_id, revoked_at__isnull=True).exclude(
                push_token=""):
            # the same phone, signed in by someone else since: only the newest holder (F-141)
            if d.push_token_at and Device.objects.filter(
                    push_token=d.push_token, push_token_at__gt=d.push_token_at).exists():
                continue
            if fcm.send(d.push_token, {"id": str(n.id)}):
                ok += 1
            else:
                failed += 1
                Device.objects.filter(pk=d.pk).update(push_token="")
        Notification.objects.filter(pk=n.pk).update(pushed=ok, push_failed=failed)
        sent += ok
    logging.getLogger(__name__).info("pushes sent", extra={"notifications": len(ids),
                                                           "sent": sent})
    return sent


@shared_task
def late_starts() -> int:
    """Every 5 min: jobs past their time by more than the Settings late-start limit and not
    started → Ops hear once per job. Also drops bell rows older than 30 days."""
    from apps.bookings import timing
    from apps.bookings.models import Booking

    from .handlers import _when, to_ops

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
               f"{mins} min past {_when(None, b.answers.get('inspection_time'))}")
        count += 1
    return count
