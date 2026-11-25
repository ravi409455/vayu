"""Submitted -> Completed once the files are in; Ops finishing without the missing ones."""

from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.bookings import activity
from apps.bookings.changes import stamp
from apps.bookings.models import Booking
from apps.bookings.services import err
from apps.core import events
from apps.forms.models import Field

from ..models import KINDS, MediaAsset
from .answers import expected_media


def check_completion(booking_id: Any) -> bool:
    """Submitted -> Completed once every referenced file is verified. Exactly once."""
    with transaction.atomic():
        b = Booking.objects.select_for_update().get(pk=booking_id)
        if b.stage != "submitted" or b.conflict:      # a conflict waits for Ops to choose
            return False
        insp = b.counted_inspection()
        if insp is None:
            return False
        ids = expected_media(insp)
        verified = set(map(str, MediaAsset.objects.filter(
            booking=b, id__in=list(ids), status="verified").values_list("id", flat=True)))
        if verified != ids:
            return False
        b.stage = "completed"
        stamp(b, None, ["stage"])
        b.save()
        activity.log(b, None, "changed", {"stage": ["submitted", "completed"]})
    # a stage change is a booking.updated like any other (H-13); before inspection.completed so
    # the report made for the completion is not marked out of date by it
    events.emit("booking.updated", booking=str(b.id), booking_id=b.booking_id,
                changes={"stage": ["submitted", "completed"]}, by=None)
    events.emit("inspection.completed", booking=str(b.id), booking_id=b.booking_id,
                inspection=str(insp.id))
    events.emit("media.completed", booking=str(b.id), booking_id=b.booking_id)
    return True


def missing_files(booking: Booking) -> list[dict[str, Any]]:
    """What holds a submitted job back: per field of the counted inspection, the files it names
    that have not arrived, and whether the field is required (Ops upload those before finishing)."""
    from apps.forms.rules import evaluate_form, spec_from_version

    insp = booking.counted_inspection()
    if booking.stage != "submitted" or insp is None:
        return []
    arrived = set(map(str, MediaAsset.objects.filter(booking=booking, status="verified")
                      .values_list("id", flat=True)))
    today = timezone.localdate().isoformat()
    rows = []
    pinned = insp.pinned()
    for part in ("start", "inspection", "end"):     # page order: check-in, inspection, wrap-up
        version = pinned.get(part)
        if version is None:
            continue
        answers = insp.answers.get(part) or {}
        required = evaluate_form(spec_from_version(version), insp.answers, today).required
        for f in Field.objects.filter(version=version, type__in=KINDS).order_by("order", "id"):
            value = answers.get(f.key)
            gone = [i for i in ([value] if isinstance(value, str) else value or [])
                    if str(i) not in arrived]
            if gone:
                rows.append({"part": part, "key": f.key, "label": f.label, "count": len(gone),
                             "required": bool(required.get(f.key))})
    return rows


def finish_without_missing(actor: Any, booking: Booking) -> Booking:
    """Ops finish a job whose expert's files will not come (a lost phone): only once every
    required field has its file. Missing optional files are left out of the report; if they
    arrive later they are added and the report is made again (verify_asset)."""
    with transaction.atomic():
        b = Booking.objects.select_for_update().get(pk=booking.pk)
        if b.stage != "submitted":
            raise err("INVALID_STAGE", "Only a booking waiting for its files can be finished.", 409)
        if b.conflict:
            raise err("CONFLICT_OPEN", "Choose which inspection counts first.", 409)
        rows = missing_files(b)
        need = [r for r in rows if r["required"]]
        if need:
            raise err("REQUIRED_FILES_MISSING", "Upload the required files first: "
                      + ", ".join(r["label"] for r in need) + ".", 409,
                      keys=[f"{r['part']}.{r['key']}" for r in need])
        insp = b.counted_inspection()
        b.stage = "completed"
        stamp(b, actor, ["stage"], edited=False)
        b.save()
        left = sum(r["count"] for r in rows)
        activity.log(b, actor, "finished_without_files",
                     {"stage": ["submitted", "completed"], "missing": left},
                     keys=["stage", *(f"{r['part']}.{r['key']}" for r in rows)], inspection=insp)
    events.emit("booking.updated", booking=str(b.id), booking_id=b.booking_id,
                changes={"stage": ["submitted", "completed"]}, by=actor.pk)
    events.emit("inspection.completed", booking=str(b.id), booking_id=b.booking_id,
                inspection=str(insp.id) if insp else "")
    return b
