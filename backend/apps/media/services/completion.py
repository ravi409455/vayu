"""Submitted -> Completed once the files are in; Ops finishing without the missing ones."""

from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.bookings import activity
from apps.bookings.changes import stamp
from apps.bookings.models import Booking
from apps.core import events
from apps.core.errors import fail
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


PART_WORD = {"start": "Check-in", "inspection": "Inspection", "end": "Wrap-up"}
REASONS = {"customer_waiting": "customer is waiting", "phone_lost": "phone lost or broken",
           "other": "other"}


def missing_files(booking: Booking) -> list[dict[str, Any]]:
    """What holds a submitted job back: per field of the counted inspection, the files it names
    that have not arrived (`ids`, so an Ops upload can take each one's place), of how many, where
    the field is, and whether it is required."""
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
        # with the booking's answers: a rule may look at them (e.g. the inspection type)
        required = evaluate_form(spec_from_version(version),
                                 {"booking": booking.answers, **insp.answers}, today).required
        for f in (Field.objects.filter(version=version, type__in=KINDS)
                  .select_related("section").order_by("order", "id")):
            value = answers.get(f.key)
            named = [str(i) for i in ([value] if isinstance(value, str) else value or [])]
            gone = [i for i in named if i not in arrived]
            if gone:
                rows.append({"part": part, "key": f.key, "label": f.label, "count": len(gone),
                             "required": bool(required.get(f.key)), "ids": gone, "of": len(named),
                             "page": PART_WORD[part], "section": f.section.title})
    return rows


def expert_phone(booking: Booking) -> dict[str, Any] | None:
    """The submitting expert's live phone: when it was last seen and how many files it still
    holds, so Ops can tell "still sending" from "lost". None when there is no live phone."""
    from apps.accounts.models import Device

    insp = booking.counted_inspection()
    if insp is None:
        return None
    d = (Device.objects.filter(user_id=insp.expert_id, revoked_at__isnull=True)
         .order_by("-last_seen_at").first())
    if d is None:
        return None
    return {"last_seen_at": d.last_seen_at, "files": (d.unsynced or {}).get("files")}


def finish_without_missing(actor: Any, booking: Booking, reason: str = "",
                           note: str = "") -> Booking:
    """Ops finish a job whose expert's files will not come (a lost phone, a customer who wants
    the report now), even with required files missing (owner, 2026-11-27): the report uses its
    stand-in image for them. Files that arrive later are added and the report is marked out of
    date (Ops press Regenerate)."""
    if reason and reason not in REASONS:
        raise fail("VALIDATION_ERROR", "Pick a reason from the list.", 400)
    note = (note or "").strip()[:300]
    with transaction.atomic():
        b = Booking.objects.select_for_update().get(pk=booking.pk)
        if b.stage != "submitted":
            raise fail("INVALID_STAGE", "Only a booking waiting for its files can be finished.",
                       409)
        if b.conflict:
            raise fail("CONFLICT_OPEN", "Choose which inspection counts first.", 409)
        rows = missing_files(b)
        insp = b.counted_inspection()
        b.stage = "completed"
        stamp(b, actor, ["stage"], edited=False)
        b.save()
        left = sum(r["count"] for r in rows)
        changes: dict[str, Any] = {"stage": ["submitted", "completed"], "missing": left,
                                   "required": sum(r["count"] for r in rows if r["required"])}
        if reason:
            changes["reason"] = reason
        if note:
            changes["note"] = note
        activity.log(b, actor, "finished_without_files", changes,
                     keys=["stage", *(f"{r['part']}.{r['key']}" for r in rows)], inspection=insp)
    events.emit("booking.updated", booking=str(b.id), booking_id=b.booking_id,
                changes={"stage": ["submitted", "completed"]}, by=actor.pk)
    events.emit("inspection.completed", booking=str(b.id), booking_id=b.booking_id,
                inspection=str(insp.id) if insp else "")
    return b
