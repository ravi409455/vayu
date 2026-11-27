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
    only viewable in the app. Per form, the newest published version decides, so turning it on
    reaches older bookings too (a field it no longer has keeps its own version's setting). Files
    are kept by key alone, so a key hidden by any of the booking's forms stays hidden."""
    from apps.forms.models import FormVersion, VersionStatus

    pinned = {v for i in booking.inspections.all() for v in i.pinned().values() if v is not None}
    if not pinned:
        return set()
    newest = {v.form_id: v for v in FormVersion.objects.filter(
        form_id__in={v.form_id for v in pinned}, status=VersionStatus.PUBLISHED).order_by("number")}
    setting: dict[tuple[int, str], dict[int, bool]] = {}     # (form, key) -> {version: hidden}
    for vid, form_id, key, config in Field.objects.filter(
            version__in={*pinned, *newest.values()}, type__in=KINDS).values_list(
            "version_id", "version__form_id", "key", "config"):
        setting.setdefault((form_id, key), {})[vid] = (config or {}).get(
            "hide_from_customer") is True
    hidden = set()
    for (form_id, key), by_version in setting.items():
        top = newest.get(form_id)
        if top is not None and top.id in by_version:
            on = by_version[top.id]                      # the newest version decides
        else:
            on = any(by_version.values())                # gone from it: what the booking used
        if on:
            hidden.add(key)
    return hidden
