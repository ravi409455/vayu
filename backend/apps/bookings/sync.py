"""What an expert's phone downloads to work without signal: their jobs, the form versions those jobs
use (only the ones the phone doesn't have yet), the master lists, and what Ops changed since the
phone last synced (for the "Ops changed old -> new" banner)."""
from datetime import timedelta

from django.db.models import Prefetch, Q
from django.utils import timezone

from apps.core.errors import CodedError
from apps.forms.models import Form, FormType, FormVersion, MasterList, VersionStatus

from . import activity
from .models import Booking, Inspection
from .serializers import BookingSerializer
from .submissions import form_for_role, inspection_version, own_filter, versions_to_pin

ACTIVE = ("assigned", "in_progress", "submitted")
DONE_DAYS = 7          # finished jobs stay on the phone's Done tab this long
MOVED_LIST_DAYS = 2    # a job moved away stays listed (for submit or discard) this long


def jobs_for(user):
    recent = timezone.localdate() - timedelta(days=DONE_DAYS)
    # also an open job Ops moved away from this expert lately: their phone may hold work for it
    # done offline (it shows only where it does, with "Discard draft / Submit anyway")
    moved = Q(activity__changes__assigned_expert__0=user.pk,
              activity__at__gte=timezone.now() - timedelta(days=MOVED_LIST_DAYS),
              stage__in=ACTIVE, inspection_date__gte=recent)
    return (Booking.objects.filter(own_filter(user) | moved)
            .filter(Q(stage__in=ACTIVE) | Q(inspection_date__gte=recent))
            .select_related("report", "last_edited_by", "released_by")
            .prefetch_related("reschedules__by", Prefetch(
                "inspections", queryset=Inspection.objects.select_related(
                    "form_version", "start_version", "end_version").order_by("created_at")))
            .distinct().order_by("inspection_date", "created_at"))


def _pins(b: Booking, by_type: dict) -> dict:
    """current_versions(b) from the prefetched inspections; what a new start would pin is worked
    out once per inspection type."""
    inspections = list(b.inspections.all())
    if inspections:
        return inspections[-1].pinned()
    if b.inspection_type not in by_type:
        try:
            by_type[b.inspection_type] = versions_to_pin(inspection_version(b.inspection_type))
        except CodedError:       # no published form for its type: listed, but nothing to fill yet
            by_type[b.inspection_type] = {}
    return by_type[b.inspection_type]


def payload(user, have: set[int], since, context, drafts: set[int] | None = None) -> dict:
    """[drafts]: form versions the phone's open drafts are pinned to. They are sent too (when the
    phone lacks them), even once no listed job uses them: the phone keeps every one of them."""
    jobs = []
    versions = {v.id: v for v in FormVersion.objects.filter(
        pk__in=(drafts or set()) - have, status=VersionStatus.PUBLISHED,
        form__type__in=(FormType.CUSTOM, FormType.START, FormType.END))}
    bookings = list(jobs_for(user))
    by_type: dict = {}
    for b in bookings:
        pinned = _pins(b, by_type)
        for v in pinned.values():
            if v is not None and v.id not in have:
                versions[v.id] = v
        # a draft Ops force-released still counts: the phone may yet send it
        draft = next((i for i in reversed(b.inspections.all()) if i.expert_id == user.pk
                      and i.status in ("draft", "released")), None)
        report = getattr(b, "report", None)
        jobs.append({**BookingSerializer(b, context=context).data,
                     # the finished job's PDF, in a word (no link: experts don't open it)
                     "report": report.status if report else None,
                     "assigned_to_me": b.assigned_expert_id == user.pk,
                     "my_draft": str(draft.id) if draft else None,
                     "versions": {part: v.id if v else None for part, v in pinned.items()}})
    # what others changed, filtered exactly like the booking's history (fields the expert may not
    # see are left out; values only for the schedule / stage / assignment keys, as before)
    timelines = (activity.for_bookings(bookings, user, since=since, values=False)
                 if since is not None else {})
    changes = [{"booking": str(b.id), "booking_id": b.booking_id, **row}
               for b in bookings for row in timelines.get(b.id, [])]
    lists = {ml.key: [{"key": i.key, "label": i.label}
                      for i in sorted(ml.items.all(), key=lambda i: (i.order, i.label))
                      if not i.archived]
             for ml in MasterList.objects.prefetch_related("items")}
    # names only for the types of the expert's own jobs
    mine = {b.inspection_type for b in bookings}
    types = dict(Form.objects.filter(type="custom", inspection_type__in=mine)
                 .exclude(inspection_type="").values_list("inspection_type", "name"))
    return {"server_time": timezone.now(), "jobs": jobs, "types": types,
            "forms": {str(i): form_for_role(v, user.role, "in_progress")
                      for i, v in versions.items()},
            "lists": lists, "changes": changes}
