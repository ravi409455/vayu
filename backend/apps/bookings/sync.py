"""What an expert's phone downloads to work without signal: their jobs, the form versions those jobs
use (only the ones the phone doesn't have yet), the master lists, and what Ops changed since the
phone last synced (for the "Ops changed old -> new" banner)."""
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.core.errors import CodedError
from apps.forms.models import MasterList

from .models import Booking, BookingActivity
from .serializers import BookingSerializer
from .submissions import current_versions, form_for_role, own_filter

ACTIVE = ("assigned", "in_progress", "submitted")
DONE_DAYS = 7          # finished jobs stay on the phone's Done tab this long


def jobs_for(user):
    recent = timezone.localdate() - timedelta(days=DONE_DAYS)
    return (Booking.objects.filter(own_filter(user))
            .filter(Q(stage__in=ACTIVE) | Q(inspection_date__gte=recent))
            .distinct().order_by("inspection_date", "created_at"))


def payload(user, have: set[int], since, context) -> dict:
    jobs, versions = [], {}
    for b in jobs_for(user):
        try:
            pinned = current_versions(b)
        except CodedError:       # no published form for its type: listed, but nothing to fill yet
            pinned = {}
        for v in pinned.values():
            if v is not None and v.id not in have:
                versions[v.id] = v
        draft = b.inspections.filter(expert=user, status="draft").first()
        jobs.append({**BookingSerializer(b, context=context).data,
                     "assigned_to_me": b.assigned_expert_id == user.pk,
                     "my_draft": str(draft.id) if draft else None,
                     "versions": {part: v.id if v else None for part, v in pinned.items()}})
    changes = []
    if since is not None:
        rows = (BookingActivity.objects.filter(booking_id__in=[j["id"] for j in jobs], at__gt=since)
                .exclude(actor=user).select_related("actor", "booking").order_by("at"))
        changes = [{"booking": str(a.booking_id), "booking_id": a.booking.booking_id, "at": a.at,
                    "by": a.actor.username if a.actor else None, "kind": a.kind,
                    "changes": a.changes, "keys": a.keys} for a in rows]
    lists = {ml.key: [{"key": i.key, "label": i.label}
                      for i in sorted(ml.items.all(), key=lambda i: (i.order, i.label))
                      if not i.archived]
             for ml in MasterList.objects.prefetch_related("items")}
    return {"server_time": timezone.now(), "jobs": jobs,
            "forms": {str(i): form_for_role(v, user.role, "in_progress")
                      for i, v in versions.items()},
            "lists": lists, "changes": changes}
