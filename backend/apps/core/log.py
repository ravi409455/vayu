"""Structured application events (Q4, docs/logging.md): one JSON log line per thing that happened,
named like `booking.created`, with ids and numbers as fields, never free text with values in it.

    event("pdf.done", booking=b.booking_id, duration_ms=840, pages=12)

writes {"message": "pdf.done", "event": "pdf.done", "booking": "B-1042", "duration_ms": 840,
"pages": 12, "request_id": "…", "task_id": "…", …}. The request id (and in a worker, the task id)
are added by apps.core.logging.RequestIdFilter."""
import logging
from typing import Any

LOGGER = logging.getLogger("vayu.events")

# field names that would carry personal data or secrets: an event() with one is a bug (the
# never-log list in docs/logging.md); ids, codes, counts and durations are what events carry
NEVER = frozenset({"name", "username", "password", "phone", "address", "answers", "token",
                   "key", "api_key", "secret", "url", "email", "customer"})


def event(name: str, *, level: int = logging.INFO, user: Any = None, **fields: Any) -> None:
    """Log the event [name] with [fields]. [user]: the acting user (logged as user_id only)."""
    bad = NEVER & set(fields)
    if bad:
        raise ValueError(f"event {name!r} must not log {sorted(bad)}: see docs/logging.md")
    if user is not None:
        fields["user_id"] = getattr(user, "pk", user)
    LOGGER.log(level, name, extra={"event": name, **fields})



def on_domain_event(name: str, payload: dict[str, Any]) -> None:
    """Booking and submission events (apps.core.events) as log events: the booking's id and
    reference, the stages and the acting user's id, never the changed values."""
    b, ref, by = payload.get("booking"), payload.get("booking_id"), payload.get("by")
    if name == "booking.created":
        event("booking.created", user=by, booking=b, booking_id=ref)
    elif name == "booking.updated" and "stage" in (payload.get("changes") or {}):
        before, after = payload["changes"]["stage"]
        event("booking.stage_changed", user=by, booking=b, booking_id=ref, from_stage=before,
              to_stage=after)
        if after == "cancelled":
            event("booking.cancelled", user=by, booking=b, booking_id=ref)
    elif name == "booking.assigned":
        event("booking.assigned", booking=b, booking_id=ref, expert_id=payload.get("expert"))
    elif name == "alert.conflict":
        event("booking.conflict", level=logging.WARNING, booking=b, booking_id=ref,
              code=payload.get("code"))
    elif name == "inspection.submitted":
        event("submission.accepted", booking=b, inspection=payload.get("inspection"))
