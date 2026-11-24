"""Who hears about what. Each event becomes bell rows (and a push) for the people it concerns:
the assigned expert for changes to their job, every Ops person for problems and progress.
Ops can mute everything but problems (Profile → Notifications)."""
from apps.core import tasks as core_tasks

# Ops switch that covers each kind; problems have none, so they can't be muted
OPS_PREF = {"submitted": "submitted", "completed": "submitted", "started": "started",
            "late": "started", "new_booking": "new_bookings"}
PREFS = ("submitted", "started", "new_bookings")
PROBLEMS = {"alert.conflict": "Two experts inspected {bid}",
            "alert.pdf_failed": "Report failed for {bid}",
            "alert.stuck_upload": "Photos stuck for {bid}",
            "alert.type_change_rejected": "Type change wasn't applied for {bid}"}
PROGRESS = {"inspection.started": ("started", "{bid} started"),
            "inspection.submitted": ("submitted", "{bid} submitted"),
            "inspection.completed": ("completed", "{bid} completed")}
WHEN = ("inspection_date", "inspection_time")
QUIET = {"stage", "assigned_expert", *WHEN}       # told about in their own way, or not at all


def _when(date, time) -> str:
    return " ".join(str(x) for x in (date, time) if x)


def _label(key: str) -> str:
    return key.replace("_", " ").capitalize()


def _changed(changes: dict) -> str:
    keys = sorted(changes)
    if len(keys) == 1 and all(isinstance(v, str | int | type(None)) for v in changes[keys[0]]):
        old, new = changes[keys[0]]
        return f"{_label(keys[0])}: {old or '—'} → {new or '—'}"
    return ", ".join(_label(k) for k in keys)


def on_event(name: str, payload: dict) -> None:
    if name not in PROBLEMS and name not in PROGRESS and name not in (
            "booking.created", "booking.updated", "booking.assigned"):
        return
    from apps.bookings.models import Booking

    if not payload.get("booking"):
        return
    b = Booking.objects.filter(pk=payload["booking"]).select_related("created_by").first()
    if b is None:
        return
    bid, who = b.booking_id, b.answers.get("customer_name") or ""
    if name in PROBLEMS:
        to_ops(b, "problem", PROBLEMS[name].format(bid=bid), who)
    elif name in PROGRESS:
        kind, title = PROGRESS[name]
        to_ops(b, kind, title.format(bid=bid), who)
    elif name == "booking.created":
        from apps.integrations.apikeys import SERVICE_USERNAME
        if b.created_by and b.created_by.username == SERVICE_USERNAME:   # API / ERP only
            to_ops(b, "new_booking", f"New booking {bid}", who)
    elif name == "booking.assigned":
        if payload.get("expert") is None:
            return
        to_user(payload["expert"], b, "assigned", f"New job: {bid}",
                " · ".join(x for x in (who, _when(*(b.answers.get(k) for k in WHEN))) if x))
    else:
        _updated(b, payload.get("changes") or {}, bid, who)


def _updated(b, changes: dict, bid: str, who: str) -> None:
    old, new = changes.get("assigned_expert", [None, None])
    if old and old != new:
        to_user(old, b, "unassigned", f"{bid} moved to another expert", who)
    expert = b.assigned_expert_id
    if expert is None or b.stage not in ("assigned", "in_progress", "cancelled"):
        return
    if changes.get("stage", [None, None])[1] == "cancelled":
        to_user(expert, b, "cancelled", f"{bid} cancelled",
                " · ".join(x for x in (who, b.cancel_reason) if x))
    elif b.stage == "cancelled":
        return
    elif any(k in changes for k in WHEN):
        was = [changes.get(k, [b.answers.get(k)])[0] for k in WHEN]
        to_user(expert, b, "rescheduled", f"{bid} moved",
                f"{_when(*was)} → {_when(*(b.answers.get(k) for k in WHEN))}")
    elif "assigned_expert" not in changes and set(changes) - QUIET:
        to_user(expert, b, "changed", f"{bid} details changed",
                _changed({k: v for k, v in changes.items() if k not in QUIET}))


def to_user(user_id, booking, kind: str, title: str, body: str = "") -> None:
    _send([user_id], booking, kind, title, body)


def to_ops(booking, kind: str, title: str, body: str = "") -> None:
    from apps.accounts.models import Role, User

    pref = OPS_PREF.get(kind)
    users = [u.id for u in User.objects.filter(role=Role.OPS, is_active=True)
             .only("id", "notify_prefs") if pref is None or u.notify_prefs.get(pref, True)]
    _send(users, booking, kind, title, body)


def _send(user_ids, booking, kind, title, body) -> None:
    if not user_ids:
        return
    from .models import Notification
    from .tasks import push

    rows = Notification.objects.bulk_create(
        Notification(user_id=u, booking=booking, kind=kind, title=title[:200], body=body[:300])
        for u in user_ids)
    ids = [n.id for n in rows]
    # sent after the commit: never push about a change that was rolled back
    core_tasks.after_commit(lambda: push.delay(ids))
