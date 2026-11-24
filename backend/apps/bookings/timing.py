"""Started late / finished too quickly. The raw minutes are stored on the booking when the
server gets Start and Submit (server clock only); the limits come from the "timing" setting at
read time, so changing a limit re-flags old jobs at once."""
from datetime import datetime

from django.db.models import Q
from django.utils import timezone

from apps.core import app_settings


def slot(b) -> datetime | None:
    """The booked start as an aware datetime (local time), or None when it is not set."""
    t = b.answers.get("inspection_time")
    if b.inspection_date is None or not isinstance(t, str) or ":" not in t:
        return None
    h, m = (int(x) for x in t.split(":")[:2])
    d = b.inspection_date
    return timezone.make_aware(datetime(d.year, d.month, d.day, h, m))


def _minutes(delta) -> int:
    return round(delta.total_seconds() / 60)


def stamp_late(b) -> None:
    """At Start: minutes after the booked time (negative = early); None if either is unknown."""
    booked = slot(b)
    b.late_minutes = _minutes(b.started_at - booked) if b.started_at and booked else None


def stamp_duration(b, submitted_at) -> None:
    """At Submit: minutes from the server's Start to its Submit; None if Start never arrived."""
    b.duration_minutes = _minutes(submitted_at - b.started_at) if b.started_at else None


def config() -> dict:
    return app_settings.get("timing")


def min_for(inspection_type: str, cfg: dict) -> int:
    return cfg["min_minutes_by_type"].get(inspection_type, cfg["min_minutes_default"])


def late_q(cfg: dict) -> Q:
    return Q(late_minutes__gt=cfg["late_grace_minutes"])


def quick_q(cfg: dict) -> Q:
    by_type = cfg["min_minutes_by_type"]
    q = Q(duration_minutes__lt=cfg["min_minutes_default"]) & ~Q(inspection_type__in=list(by_type))
    for t, m in by_type.items():
        q |= Q(inspection_type=t, duration_minutes__lt=m)
    return q


def flags(b, cfg: dict) -> dict:
    late = b.late_minutes is not None and b.late_minutes > cfg["late_grace_minutes"]
    need = min_for(b.inspection_type, cfg)
    quick = b.duration_minutes is not None and b.duration_minutes < need
    return {"late_minutes": b.late_minutes, "duration_minutes": b.duration_minutes,
            "late": late, "quick": quick, "min_minutes": need,
            "grace_minutes": cfg["late_grace_minutes"],
            **{f"{f}_reviewed_{k}": _reviewed(b, f, k)
               for f in ("late", "quick") for k in ("by", "at")}}


def _reviewed(b, flag: str, what: str):
    v = getattr(b, f"{flag}_reviewed_{what}")
    return None if v is None else v.shown_name if what == "by" else v.isoformat()
