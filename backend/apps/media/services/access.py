"""Who may read or add media on a booking, and which fields are hidden from them."""


from typing import Any

from rest_framework.request import Request

from apps.accounts.permissions import scope_for
from apps.bookings.models import Booking
from apps.bookings.services import err
from apps.bookings.submissions import current_versions, deliver_filter, own_filter
from apps.core.errors import CodedError
from apps.forms.access import hidden_inspection_forms, levels_for
from apps.forms.models import Field

from ..models import KINDS, MediaAsset


def writable_booking(request: Request, booking_id: Any, moved_ok: bool = False) -> Booking:
    """The booking if this user may add media to it: its expert (own scope) or media managers.
    [moved_ok]: also a job moved away from them meanwhile, for their own new or own uploads only."""
    user = request.user
    qs = Booking.objects.all()
    if scope_for(user, "media.manage", request) is None \
            and scope_for(user, "submissions.fill", request) == "own":
        qs = qs.filter(deliver_filter(user) if moved_ok else own_filter(user)).distinct()
    b = qs.filter(pk=booking_id).first()
    if b is None:
        raise err("NOT_FOUND", f"{word(user).capitalize()} not found.", 404)
    return b


def word(user: Any) -> str:
    """What this person calls a booking (docs/plan-leads-bookings-words.md): experts a lead."""
    return "lead" if getattr(user, "role", "") == "expert" else "booking"


def readable_booking(request: Request, booking_id: Any) -> Booking:
    qs = Booking.objects.all()
    if scope_for(request.user, "submissions.view", request) == "own":
        qs = qs.filter(own_filter(request.user)).distinct()
    b = qs.filter(pk=booking_id).first()
    if b is None:
        raise err("NOT_FOUND", f"{word(request.user).capitalize()} not found.", 404)
    return b


def field_for(booking: Booking, field_key: str) -> Field:
    """The form field (custom, start or end form) a media upload belongs to."""
    for v in current_versions(booking).values():
        f = Field.objects.filter(version=v, key=field_key).first() if v else None
        if f is not None:
            return f
    raise err("UNKNOWN_FIELD", f"'{field_key}' is not a field of this inspection.")


def hidden_fields(user: Any, booking: Booking) -> set[str]:
    """Media field keys this user may not see at the booking's current stage (an expert's own
    form too: Ops-only photo fields stay Ops-only)."""
    if user.role == "admin":
        return set()
    try:
        pinned = current_versions(booking)
    except CodedError:       # no form says what this user may see: fail closed, hide every file
        return set(MediaAsset.objects.filter(booking=booking).values_list("field_key", flat=True))
    main, versions = pinned["inspection"], list(pinned.values())
    out: set[str] = set()
    if main.form_id in hidden_inspection_forms(user):          # the whole submission is off limits
        out |= set(Field.objects.filter(version=main, type__in=KINDS).values_list("key", flat=True))
    for v in versions:
        if v is not None:
            out |= {k for k, level in levels_for(v, user.role, booking.stage).items()
                    if level == "hidden"}
    return out


def is_manager(user: Any, request: Request | None = None) -> bool:
    return scope_for(user, "media.manage", request) is not None
