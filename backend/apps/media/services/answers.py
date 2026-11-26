"""Which files an inspection's answers name, and which of them never arrived."""

from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError

from apps.bookings.models import Booking, Inspection
from apps.core.errors import fail
from apps.forms.fieldtypes import DEFAULT_MAX_COUNT
from apps.forms.models import Field

from ..models import KINDS, MediaAsset


def submitted_answer(booking: Booking, field: Field, lock: Any=False) -> Any:
    """(inspection, part, file ids) of a field in the submitted inspection. Not during a
    conflict: the late inspection does not count, the customer's can't change until Ops choose."""
    if booking.conflict:
        raise fail("CONFLICT_OPEN", "Choose which inspection counts first.", 409)
    qs = booking.inspections.filter(status="submitted").order_by("-submitted_at")
    insp = (qs.select_for_update() if lock else qs).first()
    part = next((p for p, v in (insp.pinned() if insp else {}).items()
                 if v is not None and v.id == field.version_id), None)
    if insp is None or part is None:
        raise fail("NOT_SUBMITTED", "Files can be added only after the expert submits.", 409)
    value = (insp.answers.get(part) or {}).get(field.key)
    return insp, part, [value] if isinstance(value, str) else list(value or [])


def live_asset(booking: Booking, field_key: str, asset_id: Any) -> MediaAsset | None:
    """A file on this booking's field that has not been replaced."""
    try:
        return MediaAsset.objects.filter(booking=booking, field_key=field_key,
                                         replaced_at__isnull=True, pk=asset_id).first()
    except (ValueError, DjangoValidationError):     # not a UUID
        return None


# never checked in: not verified or purged
NEVER_ARRIVED = ("pending", "uploaded", "verifying", "failed")


def unarrived(booking: Booking, ids: list[str]) -> list[str]:
    """Files a field names that never arrived (the expert's phone lost or broken), oldest first.
    Only while the job is waiting for its files; a file that arrived (even if later purged by the
    retention setting) never counts."""
    if booking.stage != "submitted":
        return []
    lost = set(map(str, MediaAsset.objects.filter(
        booking=booking, id__in=ids, status__in=NEVER_ARRIVED).values_list("id", flat=True)))
    return [i for i in ids if i in lost]


def first_unarrived(booking: Booking, ids: list[str]) -> str | None:
    return next(iter(unarrived(booking, ids)), None)


def referenced_ids(version: Any, answers: dict[str, Any]) -> dict[str, str]:
    """{media id: field type} for every media reference in one form's cleaned answers."""
    out: dict[str, str] = {}
    for f in Field.objects.filter(version=version, type__in=KINDS):
        value = answers.get(f.key)
        for mid in ([value] if isinstance(value, str) else value or []):
            out[str(mid)] = f.type
    return out


def reference_errors(booking: Booking, parts: list[tuple[Any, ...]]) -> dict[str, str]:
    """Answers may only point at this booking's media of the right kind."""
    errors: dict[str, str] = {}
    for version, answers in parts:
        refs = referenced_ids(version, answers)
        found = {str(a.id): a for a in MediaAsset.objects.filter(booking=booking,
                                                                  id__in=list(refs))}
        for f in Field.objects.filter(version=version, type__in=KINDS):
            value = answers.get(f.key)
            for mid in ([value] if isinstance(value, str) else value or []):
                asset = found.get(str(mid))
                if asset is None:
                    errors[f.key] = "UNKNOWN_MEDIA"
                elif asset.kind != f.type or asset.field_key != f.key:
                    errors[f.key] = "WRONG_MEDIA_KIND"
    return errors


def expected_media(inspection: Inspection) -> set[str]:
    ids: set[str] = set()
    for part, version in inspection.pinned().items():
        if version is not None:
            ids |= set(referenced_ids(version, inspection.answers.get(part) or {}))
    return ids

def max_count(field: Field) -> int:
    if field.type == "signature":
        return 1
    return int(field.config.get("max_count", DEFAULT_MAX_COUNT.get(field.type, 1)))
