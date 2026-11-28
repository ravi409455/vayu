"""checkin.completed (docs/plan-checkin-event.md): one event per check-in, fired by a worker when
every file the check-in names is verified, or WAIT after the check-in reached the server.

Start and the file check only queue `tasks.checkin_check`; nothing here runs inside a phone's
request, so a fault in it can never fail a live inspection."""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.core import events, log
from apps.core import tasks as core_tasks

from .models import Inspection

WAIT = timedelta(minutes=5)     # longest wait for the check-in files (owner, 2026-11-28)
BATCH = 200                     # check-ins the beat takes per run; the next run takes the rest


def files(insp: Inspection) -> set[str]:
    """Ids of the files the check-in answers name."""
    from apps.media.services.answers import referenced_ids

    return set(referenced_ids(insp.start_version, insp.answers.get("start") or {}))


def _missing(insp: Inspection, unverified: set[str]) -> list[str]:
    """Labels of the check-in fields with a file that is not verified."""
    from apps.forms.models import Field

    start = insp.answers.get("start") or {}
    out = []
    for f in Field.objects.filter(version=insp.start_version).order_by(
            "section__page__order", "section__order", "order", "id"):
        value = start.get(f.key)
        ids = [value] if isinstance(value, str) else value if isinstance(value, list) else []
        if any(str(i) in unverified for i in ids):
            out.append(f.label)
    return out


def queue_for_booking(booking_id) -> None:
    """A file of this booking was verified: check its check-ins still waiting (in the worker)."""
    from .tasks import checkin_check

    for pk in Inspection.objects.filter(booking_id=booking_id, checkin_sent_at__isnull=True,
                                        checkin_due_at__isnull=False).values_list("pk", flat=True):
        checkin_check.delay(str(pk))


def maybe_fire(insp_id, now=None, arrived: bool = False) -> bool:
    """Fire the check-in's event if its files are all verified or its wait is over. Exactly once:
    the row lock and checkin_sent_at decide when two callers race. [arrived]: called for the
    check-in that just reached the server (logs that it waits)."""
    from apps.media.models import MediaAsset

    now = now or timezone.now()
    with transaction.atomic():
        insp = (Inspection.objects.select_for_update().filter(
            pk=insp_id, checkin_sent_at__isnull=True, checkin_due_at__isnull=False).first())
        if insp is None:                    # sent already, from before this change, or deleted
            return False
        due = insp.checkin_due_at or now               # set: the filter above
        ids = files(insp)
        verified = {str(i) for i in MediaAsset.objects.filter(
            pk__in=ids, status="verified").values_list("pk", flat=True)}
        timed_out = now >= due
        if ids - verified and not timed_out:
            if arrived:
                log.event("checkin.waiting", booking=str(insp.booking_id),
                          inspection=str(insp.id), files=len(ids - verified))
            return False
        insp.checkin_sent_at = now
        insp.save(update_fields=["checkin_sent_at"])
        missing = _missing(insp, ids - verified)
        number = Inspection.objects.filter(booking_id=insp.booking_id,
                                           start_version__isnull=False,
                                           created_at__lte=insp.created_at).count()
        booking = insp.booking
        log.event("checkin.fired", booking=str(booking.id),
                  inspection=str(insp.id), number=number, missing=len(missing),
                  timed_out=bool(ids - verified),
                  waited_s=round((now - (due - WAIT)).total_seconds()))
        payload = {"booking": str(booking.id), "booking_id": booking.booking_id,
                   "inspection": str(insp.id), "missing": missing, "number": number}
        core_tasks.after_commit(lambda: events.emit("checkin.completed", **payload))
    return True
