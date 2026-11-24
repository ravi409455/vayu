"""What an expert's phone downloads to work without signal: their jobs, the form versions those jobs
use (only the ones the phone doesn't have yet), the master lists, and what Ops changed since the
phone last synced (for the "Ops changed old -> new" banner)."""
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.core.errors import CodedError
from apps.forms.models import Form, MasterList

from . import activity
from .models import Booking
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
    bookings = list(jobs_for(user))
    for b in bookings:
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
    # what others changed, filtered exactly like the booking's history (fields the expert may not
    # see are left out, values included only for safe keys)
    changes = [{"booking": str(b.id), "booking_id": b.booking_id, **row}
               for b in bookings if since is not None
               for row in activity.for_user(b, user, since=since)]
    lists = {ml.key: [{"key": i.key, "label": i.label}
                      for i in sorted(ml.items.all(), key=lambda i: (i.order, i.label))
                      if not i.archived]
             for ml in MasterList.objects.prefetch_related("items")}
    types = dict(Form.objects.filter(type="custom").exclude(inspection_type="")
                 .values_list("inspection_type", "name"))
    return {"server_time": timezone.now(), "jobs": jobs, "types": types,
            "forms": {str(i): form_for_role(v, user.role, "in_progress")
                      for i, v in versions.items()},
            "lists": lists, "changes": changes}
