"""Volume dashboards: bookings per period x dimension, with CSV export."""
import csv
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from django.http import HttpResponse
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import perm, scope_for

from .models import Booking, Inspection

GROUPS = ("day", "week", "month")
DIMENSIONS = {"type": "inspection_type", "city": "city", "expert": "assigned_expert_id",
              "stage": "stage", "lead_owner": "answers__lead_owner"}


def csv_safe(value: str) -> str:
    """Stop spreadsheets from running a cell that starts like a formula."""
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def period_label(d: date, group: str) -> str:
    if group == "day":
        return d.isoformat()
    if group == "month":
        return f"{d.year}-{d.month:02d}"
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def volume_rows(group: str, by: str, date_from: date | None, date_to: date | None) -> list[dict]:
    qs = Booking.objects.exclude(inspection_date=None)
    if date_from:
        qs = qs.filter(inspection_date__gte=date_from)
    if date_to:
        qs = qs.filter(inspection_date__lte=date_to)
    counts: Counter = Counter()
    for day, key in qs.values_list("inspection_date", DIMENSIONS[by]):
        counts[(period_label(day, group), "" if key is None else str(key))] += 1
    return [{"period": p, "key": k, "count": n} for (p, k), n in sorted(counts.items())]


class DashboardVolume(APIView):
    permission_classes = [perm("dashboards.view")]
    declared_permissions = ("dashboards.view", "dashboards.export")

    def get(self, request):
        q = request.query_params
        if q.get("group") not in GROUPS or q.get("by") not in DIMENSIONS:
            raise ValidationError({"detail": f"group must be one of {GROUPS}; by one of "
                                             f"{tuple(DIMENSIONS)}."})
        bounds = []
        for name in ("date_from", "date_to"):
            try:
                bounds.append(date.fromisoformat(q[name]) if q.get(name) else None)
            except ValueError as e:
                raise ValidationError({name: "Use YYYY-MM-DD."}) from e
        rows = volume_rows(q["group"], q["by"], *bounds)
        if q.get("export") == "csv":
            if scope_for(request.user, "dashboards.export", request) is None:
                raise PermissionDenied("You may not export dashboard data.")
            response = HttpResponse(content_type="text/csv")
            response["Content-Disposition"] = 'attachment; filename="volume.csv"'
            writer = csv.DictWriter(response, fieldnames=["period", "key", "count"])
            writer.writeheader()
            writer.writerows({**r, "key": csv_safe(r["key"])} for r in rows)
            return response
        return Response({"rows": rows})


ON_TIME_GRACE = timedelta(minutes=15)   # started up to 15 minutes after the slot counts as on time


def _bounds(q) -> tuple[date, date]:
    """date_from / date_to (inclusive); the last 30 days when not given."""
    try:
        end = date.fromisoformat(q["date_to"]) if q.get("date_to") else timezone.localdate()
        start = (date.fromisoformat(q["date_from"]) if q.get("date_from")
                 else end - timedelta(days=29))
    except ValueError as e:
        raise ValidationError({"detail": "Use YYYY-MM-DD for date_from and date_to."}) from e
    if start > end:
        raise ValidationError({"detail": "date_from must not be after date_to."})
    return start, end


def _slot(b: Booking) -> datetime | None:
    """The booked start as an aware datetime (local time), or None when it is not set."""
    t = b.answers.get("inspection_time")
    if b.inspection_date is None or not isinstance(t, str) or ":" not in t:
        return None
    h, m = (int(x) for x in t.split(":")[:2])
    naive = datetime(b.inspection_date.year, b.inspection_date.month, b.inspection_date.day, h, m)
    return timezone.make_aware(naive)


def _stats(bookings: list[Booking], visits: dict) -> dict:
    """Headline numbers for one set of bookings. visits: booking id -> (started, submitted)."""
    total = len(bookings)
    done = sum(b.stage == "completed" for b in bookings)
    cancelled = sum(b.stage == "cancelled" for b in bookings)
    minutes, on_time, timed = [], 0, 0
    for b in bookings:
        started, submitted = visits.get(b.pk, (None, None))
        if started and submitted:
            minutes.append((submitted - started).total_seconds() / 60)
        slot = _slot(b)
        if started and slot:
            timed += 1
            on_time += started <= slot + ON_TIME_GRACE
    live = total - cancelled
    return {"bookings": total, "completed": done, "cancelled": cancelled,
            "completion_rate": round(100 * done / live, 1) if live else None,
            "avg_minutes": round(sum(minutes) / len(minutes)) if minutes else None,
            "on_time": round(100 * on_time / timed) if timed else None}


def summary(start: date, end: date) -> dict:
    days = (end - start).days + 1
    prev_start = start - timedelta(days=days)
    qs = list(Booking.objects.filter(inspection_date__gte=prev_start, inspection_date__lte=end))
    visits: dict = {}
    insps = Inspection.objects.filter(booking__in=qs).exclude(status="superseded")
    for i in insps.order_by("created_at"):
        visits[i.booking_id] = (i.client_started_at or i.created_at, i.submitted_at)
    now = [b for b in qs if b.inspection_date and b.inspection_date >= start]
    before = [b for b in qs if b.inspection_date and b.inspection_date < start]
    by_expert: dict = defaultdict(list)
    for b in now:
        if b.assigned_expert_id and b.stage != "cancelled":
            by_expert[b.assigned_expert_id].append(b)
    experts = [{"expert": eid, **_stats(rows, visits)} for eid, rows in by_expert.items()]
    experts.sort(key=lambda r: -r["bookings"])
    return {"date_from": start.isoformat(), "date_to": end.isoformat(),
            "period": _stats(now, visits), "previous": _stats(before, visits),
            "by_expert": experts}


class DashboardSummary(APIView):
    """Headline numbers for a period and the period just before it, and per expert."""

    permission_classes = [perm("dashboards.view")]
    declared_permissions = ("dashboards.view",)

    def get(self, request):
        return Response(summary(*_bounds(request.query_params)))
