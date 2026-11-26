"""Who may read or add media on a booking, and which fields are hidden from them."""


from typing import Any

from rest_framework.request import Request

from apps.accounts.permissions import scope_for
from apps.bookings.models import Booking
from apps.bookings.submissions import current_versions, deliver_filter, own_filter
from apps.core.errors import CodedError, fail
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
        raise fail("NOT_FOUND", f"{word(user).capitalize()} not found.", 404)
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
        raise fail("NOT_FOUND", f"{word(request.user).capitalize()} not found.", 404)
    return b


def field_for(booking: Booking, field_key: str) -> Field:
    """The form field (custom, start or end form) a media upload belongs to."""
    for v in current_versions(booking).values():
        f = Field.objects.filter(version=v, key=field_key).first() if v else None
        if f is not None:
            return f
    raise fail("UNKNOWN_FIELD", f"'{field_key}' is not a field of this inspection.")


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


def customer_hidden(booking: Booking) -> set[str]:
    """Keys of the file fields marked "Hide from customer" (owner, 2026-11-27: payment and other
    internal photos): never in the report, its download links, partner integrations or any ZIP;
    only viewable in the app. The newest published version of each form decides, so turning it on
    reaches older bookings too; a field it no longer has keeps its own version's setting."""
    from apps.forms.models import FormVersion, VersionStatus

    pinned = {v for i in booking.inspections.all() for v in i.pinned().values() if v is not None}
    if not pinned:
        return set()
    newest = {}
    for v in FormVersion.objects.filter(form_id__in={v.form_id for v in pinned},
                                        status=VersionStatus.PUBLISHED).order_by("number"):
        newest[v.form_id] = v                                  # highest number wins
    hidden: dict[str, bool] = {}
    # pinned first, then newest over it: the newest version's setting wins for a key it has
    for versions in (pinned, set(newest.values()) - pinned):
        for key, config in Field.objects.filter(version__in=versions, type__in=KINDS
                                                ).values_list("key", "config"):
            hidden[key] = (config or {}).get("hide_from_customer") is True
    return {k for k, v in hidden.items() if v}
