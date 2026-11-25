"""Volume dashboards: bookings per period x dimension, with CSV export."""
import csv
from collections import Counter
from datetime import date, timedelta

from django.db.models import Avg, Count, Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import perm, scope_for

from . import timing
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


STAGE_LABELS = {"draft": "Unassigned", "assigned": "Assigned", "in_progress": "In progress",
                "submitted": "Uploading", "completed": "Completed", "cancelled": "Cancelled"}


def key_labels(by: str, keys: set[str]) -> dict[str, str]:
    """What a person calls each key (the screen shows the same names): the form's name for a
    type, the city's label, a person's name. A key with no name stays as it is."""
    keys = {k for k in keys if k}
    if by == "stage":
        found: dict[str, str] = {k: STAGE_LABELS[k] for k in keys if k in STAGE_LABELS}
    elif by == "type":
        from apps.forms.models import Form

        found = dict(Form.objects.filter(type="custom", inspection_type__in=keys)
                     .values_list("inspection_type", "name"))
    elif by == "city":
        from apps.forms.models import MasterListItem

        found = dict(MasterListItem.objects.filter(list__key="city", key__in=keys)
                     .values_list("key", "label"))
    else:                                                       # expert, lead_owner: user ids
        from apps.accounts.models import User

        ids = [int(k) for k in keys if k.isdigit()]
        found = {str(u.pk): u.name or u.username for u in User.objects.filter(pk__in=ids)}
    return {k: found.get(k, k) for k in keys}


def csv_filename(by: str, date_from: date | None, date_to: date | None) -> str:
    """bookings-by-type_2026-10-26_to_2026-11-24.csv: says what is inside, and for when."""
    span = "_".join(x for x in (date_from and date_from.isoformat(), date_to and
                                f"to_{date_to.isoformat()}") if x)
    return f"bookings-by-{by.replace('_', '-')}{'_' + span if span else ''}.csv"


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
            name = csv_filename(q["by"], *bounds)
            response["Content-Disposition"] = f'attachment; filename="{name}"'
            labels = key_labels(q["by"], {r["key"] for r in rows})
            writer = csv.DictWriter(response, fieldnames=["period", "key", "label", "count"])
            writer.writeheader()
            writer.writerows({**r, "key": csv_safe(r["key"]),
                              "label": csv_safe(labels.get(r["key"], "Not set"))} for r in rows)
            return response
        return Response({"rows": rows})


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
    if (end - start).days > MAX_DAYS:
        raise ValidationError({"detail": f"Choose at most {MAX_DAYS} days."})
    return start, end


MAX_DAYS = 366                     # one span a dashboard reads at once (F-092)


def _pct(n: int, of: int) -> int | None:
    return round(100 * n / of) if of else None


def _aggregates(cfg: dict) -> dict:
    """The counts one row of headline numbers needs, worked out by the database (F-092)."""
    return {"total": Count("id"), "done": Count("id", filter=Q(stage="completed")),
            "cancelled": Count("id", filter=Q(stage="cancelled")),
            "avg": Avg("duration_minutes"), "timed": Count("duration_minutes"),
            "started": Count("late_minutes"), "late": Count("id", filter=timing.late_q(cfg)),
            "quick": Count("id", filter=timing.quick_q(cfg))}


def _stats(r: dict) -> dict:
    """Headline numbers for one set of bookings (server-clock minutes, see timing.py)."""
    live = r["total"] - r["cancelled"]
    return {"bookings": r["total"], "completed": r["done"], "cancelled": r["cancelled"],
            "completion_rate": round(100 * r["done"] / live, 1) if live else None,
            "avg_minutes": round(r["avg"]) if r["avg"] is not None else None,
            "on_time": _pct(r["started"] - r["late"], r["started"]),
            "late": r["late"], "late_pct": _pct(r["late"], r["started"]),
            "quick": r["quick"], "quick_pct": _pct(r["quick"], r["timed"])}


# on_time is 100 - late_pct, so it is timing data too
TIMING_KEYS = ("on_time", "late", "late_pct", "quick", "quick_pct")


def summary(start: date, end: date) -> dict:
    days = (end - start).days + 1
    prev_start = start - timedelta(days=days)
    cfg = timing.config()
    agg = _aggregates(cfg)
    now = Booking.objects.filter(inspection_date__gte=start, inspection_date__lte=end)
    before = Booking.objects.filter(inspection_date__gte=prev_start, inspection_date__lt=start)
    rows = (now.exclude(stage="cancelled").filter(assigned_expert__isnull=False)
            .values("assigned_expert").annotate(**agg).order_by("-total", "assigned_expert"))
    experts = [{"expert": r["assigned_expert"], **_stats(r)} for r in rows]
    return {"date_from": start.isoformat(), "date_to": end.isoformat(),
            "period": _stats(now.aggregate(**agg)), "previous": _stats(before.aggregate(**agg)),
            "by_expert": experts}


class DashboardSummary(APIView):
    """Headline numbers for a period and the period just before it, and per expert."""

    permission_classes = [perm("dashboards.view")]
    declared_permissions = ("dashboards.view",)

    def get(self, request):
        out = summary(*_bounds(request.query_params))
        # timing (on time, started late, too quick) only for those who may see timing flags;
        # blanked, not removed, so every screen keeps its shape and shows a dash
        if scope_for(request.user, "bookings.review_timing", request) is None:
            for stats in [out["period"], out["previous"], *out["by_expert"]]:
                for k in TIMING_KEYS:
                    stats[k] = None
        return Response(out)
