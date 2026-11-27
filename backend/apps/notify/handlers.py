"""Who hears about what. Each event becomes bell rows (and a push) for the people it concerns:
the assigned expert for changes to their job, every Ops person for problems and progress.
Ops can mute everything but problems (Profile → Notifications)."""
from datetime import timedelta

from apps.core import tasks as core_tasks

# Ops switch that covers each kind; problems have none, so they can't be muted
OPS_PREF = {"submitted": "submitted", "completed": "submitted", "started": "started",
            "late": "started", "new_booking": "new_bookings"}
PREFS = ("submitted", "started", "new_bookings")
# Titles say what happened first and the booking ID last (owner, 2026-11-27): the phone shows a
# title on the lock screen, so a title never holds a customer's name or address.
PROBLEMS = {"alert.conflict": "Two experts inspected · {bid}",
            "alert.pdf_failed": "Report didn't build · {bid}",
            "alert.stuck_upload": "Photos stuck · {bid}",
            "alert.type_change_rejected": "Type change not applied · {bid}",
            "alert.late_work": "Late offline work · {bid}"}
PROGRESS = {"inspection.started": ("started", "Inspection started · {bid}"),
            "inspection.submitted": ("submitted", "Inspection submitted · {bid}"),
            "inspection.completed": ("completed", "Inspection completed · {bid}")}
WHEN = ("inspection_date", "inspection_time")
# told about in their own way, or internal (which inspection counts, a conflict mark)
QUIET = {"stage", "assigned_expert", "inspection", "conflict", *WHEN}
# the same problem on the same job is told again only after a while: a day for those that fire
# again and again for one cause, 10 min for the rest (each conflict needs a new submission, so a
# real one is never lost, yet nothing can flood Ops)
QUIET_FOR = {"alert.stuck_upload": timedelta(hours=24), "alert.pdf_failed": timedelta(hours=24)}
QUIET_DEFAULT = timedelta(minutes=10)


def _when(date, time) -> str:
    """"Tue 24 Nov, 9:45 am" (the server can't know the phone's "today", so always a date)."""
    from datetime import date as Date
    from datetime import time as Time

    try:
        out = Date.fromisoformat(str(date)).strftime("%a %-d %b") if date is not None else ""
    except ValueError:
        return " ".join(str(x) for x in (date, time) if x)
    try:
        t = Time.fromisoformat(str(time))
    except ValueError:
        return out
    clock = f"{t.strftime('%-I:%M')} {'am' if t.hour < 12 else 'pm'}"
    return f"{out}, {clock}" if out else clock


def _reason(key) -> str:
    """A cancel reason's words, as the list shows them ("" when unknown)."""
    from apps.forms.models import MasterListItem

    if not key:
        return ""
    return MasterListItem.objects.filter(list__key="cancel_reason", key=key).values_list(
        "label", flat=True).first() or str(key)


def _expert_view(b):
    """(fields of the booking form by key, keys the expert may not see at this stage)."""
    from apps.bookings.services import booking_form_version
    from apps.forms.access import levels_for
    from apps.forms.models import Field

    version = booking_form_version()
    levels = levels_for(version, "expert", b.stage)
    return ({f.key: f for f in Field.objects.filter(version=version)},
            {k for k, v in levels.items() if v == "hidden"})


def _label(key: str, fields: dict) -> str:
    f = fields.get(key)
    return f.label if f is not None else key.replace("_", " ").capitalize()


def _shown(f, value) -> str:
    """A value in the words the expert reads (option and list labels, never raw keys, F-240)."""
    from apps.accounts.models import User
    from apps.forms.models import MasterListItem

    if value in (None, ""):
        return "—"
    if f is None:
        return str(value)
    if f.type == "master_list":
        return (MasterListItem.objects.filter(list__key=f.config.get("list"), key=value)
                .values_list("label", flat=True).first() or str(value))
    if f.type == "user_picker":
        u = User.objects.filter(pk=value).first()
        return u.shown_name if u else str(value)
    options = {o.get("key"): o.get("label") for o in f.config.get("options") or []}
    return str(options.get(value, value))


def _changed(changes: dict, fields: dict) -> str:
    keys = sorted(changes)
    if len(keys) == 1 and all(isinstance(v, str | int | type(None)) for v in changes[keys[0]]):
        old, new = changes[keys[0]]
        f = fields.get(keys[0])
        return f"{_label(keys[0], fields)}: {_shown(f, old)} → {_shown(f, new)}"
    return ", ".join(_label(k, fields) for k in keys)


def on_event(name: str, payload: dict) -> None:
    if name not in PROBLEMS and name not in PROGRESS and name not in (
            "booking.created", "booking.updated", "booking.assigned"):
        return
    from apps.bookings.models import Booking

    if not payload.get("booking"):
        return
    b = (Booking.objects.filter(pk=payload["booking"])
         .select_related("created_by", "assigned_expert").first())
    if b is None:
        return
    bid, who = b.booking_id, b.answers.get("customer_name") or ""
    when = _when(*(b.answers.get(k) for k in WHEN))
    if name in PROBLEMS:
        to_ops(b, "problem", PROBLEMS[name].format(bid=bid), _join(who, _type(b)),
               quiet=QUIET_FOR.get(name, QUIET_DEFAULT))
    elif name in PROGRESS:
        kind, title = PROGRESS[name]
        expert = b.assigned_expert.shown_name if b.assigned_expert else ""
        to_ops(b, kind, title.format(bid=bid), _join(expert, who))
    elif name == "booking.created":
        from apps.integrations.apikeys import SERVICE_USERNAME
        if b.created_by and b.created_by.username == SERVICE_USERNAME:   # API / ERP only
            to_ops(b, "new_booking", _join("New booking", when or bid, sep=" · "), _lines(b, set()))
        if b.assigned_expert_id:                       # created with an expert already chosen
            _new_lead(b.assigned_expert_id, b, when)
    elif name == "booking.assigned":
        if payload.get("expert") is None:
            return
        _new_lead(payload["expert"], b, when)
    else:
        _updated(b, payload.get("changes") or {}, bid, _for_expert(b, who), payload.get("by"))


def _join(*parts, sep=" · ") -> str:
    return sep.join(p for p in parts if p)


def _type(b) -> str:
    """The inspection type's name ("PDI"), as Ops named its form."""
    from apps.forms.models import Form

    return (Form.objects.filter(type="custom", inspection_type=b.inspection_type)
            .values_list("name", flat=True).first() or b.inspection_type)


def _lines(b, hidden: set) -> str:
    """"PDI · Maruti Swift VXi · TST-1017" over "Radhika Iyer · Sector 45": what, then who and
    where, leaving out what [hidden] keeps from this person."""
    from apps.bookings.services import booking_form_version
    from apps.forms.models import Field

    fields = {f.key: f for f in Field.objects.filter(version=booking_form_version())}

    def value(key):
        v = b.answers.get(key)
        return "" if key in hidden or v in (None, "") else _shown(fields.get(key), v)

    return _join(_join(_type(b), value("car_make_model"), b.booking_id),
                 _join(value("customer_name"), value("address") or value("city")), sep="\n")


def _new_lead(expert, b, when: str) -> None:
    to_user(expert, b, "assigned", _join("New lead", when or b.booking_id),
            _lines(b, _expert_view(b)[1]))


def _for_expert(b, who: str) -> str:
    """The customer's name, unless the booking form hides it from experts at this stage."""
    return "" if "customer_name" in _expert_view(b)[1] else who


def _updated(b, changes: dict, bid: str, who: str, by) -> None:
    """An expert hears about changes to their job, never about their own actions. [who]: the
    customer's name as experts may see it."""
    old, new = changes.get("assigned_expert", [None, None])
    if old and old != new and old != by:
        to_user(old, b, "unassigned", f"Lead moved to another expert · {bid}", who)
    expert = b.assigned_expert_id
    if expert is None or expert == by or b.stage not in ("assigned", "in_progress", "cancelled"):
        return
    if changes.get("stage") == ["in_progress", "assigned"] and by != expert:     # force-release
        to_user(expert, b, "released", f"Lead released by Ops · {bid}",
                "Your draft there is closed. Start the lead again to carry on.")
    elif changes.get("stage", [None, None])[1] == "cancelled":
        to_user(expert, b, "cancelled", f"Lead cancelled · {bid}",
                " · ".join(x for x in (who, _reason(b.cancel_reason)) if x))
    elif b.stage == "cancelled":
        return
    elif any(k in changes for k in WHEN):
        was = [changes.get(k, [b.answers.get(k)])[0] for k in WHEN]
        to_user(expert, b, "rescheduled", f"Lead time changed · {bid}",
                f"{_when(*was)} → {_when(*(b.answers.get(k) for k in WHEN))}")
    elif "assigned_expert" not in changes and set(changes) - QUIET:
        # never what the expert may not see: not its value, not even its name (F-068)
        fields, hidden = _expert_view(b)
        told = {k: v for k, v in changes.items() if k not in QUIET and k not in hidden}
        if told:
            to_user(expert, b, "changed", f"Lead details changed · {bid}", _changed(told, fields))


def to_user(user_id, booking, kind: str, title: str, body: str = "") -> None:
    _send([user_id], booking, kind, title, body)


def to_ops(booking, kind: str, title: str, body: str = "", quiet: timedelta | None = None) -> None:
    from django.utils import timezone

    from apps.accounts.models import Role, User

    from .models import Notification

    pref = OPS_PREF.get(kind)
    users = [u.id for u in User.objects.filter(role=Role.OPS, is_active=True)
             .only("id", "notify_prefs") if pref is None or u.notify_prefs.get(pref, True)]
    if quiet:                 # ten stuck photos, or a report failing on every retry: told once
        told = set(Notification.objects.filter(
            booking=booking, kind=kind, title=title[:200],
            created_at__gte=timezone.now() - quiet,
        ).values_list("user_id", flat=True))
        users = [u for u in users if u not in told]
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
