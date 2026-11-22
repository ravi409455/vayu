"""Volume dashboards: bookings per period x dimension, with CSV export."""
import csv
from collections import Counter
from datetime import date

from django.http import HttpResponse
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import perm, scope_for

from .models import Booking

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
