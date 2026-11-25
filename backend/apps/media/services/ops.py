"""Ops adding, replacing and removing files on a submitted job."""

from django.db import transaction
from django.utils import timezone

from apps.bookings import activity
from apps.bookings.changes import stamp
from apps.bookings.models import Booking
from apps.bookings.services import err
from apps.core import events
from apps.core import tasks as core_tasks
from apps.forms.access import levels_for
from apps.forms.models import PARTS, Field

from .. import storage
from ..models import MediaAsset, MediaZip
from .access import field_for, hidden_fields, is_manager
from .answers import expected_media, first_unarrived, live_asset, max_count, submitted_answer
from .cleanup import asset_keys, drop_zips
from .completion import check_completion

OPS_KINDS = ("photo", "video", "file")


# what a file field's "allowed" setting lets in
FILE_TYPES = {"image": {"image/jpeg", "image/png"}, "pdf": {"application/pdf"}}


OPS_STAGES = ("submitted", "completed")


LOOSE_LIMIT = 10      # Ops uploads per field not in the answers (yet)


def check_ops_upload(booking: Booking, field: Field, user) -> None:
    """What Ops and Admin may put on a booking: photos, videos and files, once the expert has
    submitted, on fields the Admin has not blocked and they may see."""
    if field.key in hidden_fields(user, booking):
        raise err("UNKNOWN_FIELD", f"'{field.key}' is not a field of this inspection.")
    if user.role != "admin" and levels_for(field.version, user.role, booking.stage).get(
            field.key) != "edit":
        raise err("FIELD_ACCESS", f"You cannot change '{field.label}' at this stage.", 403)
    if field.type not in OPS_KINDS:
        raise err("OPS_UPLOAD_NOT_ALLOWED", "Ops can add only photos, videos and files.", 403)
    if booking.stage not in OPS_STAGES:
        raise err("NOT_SUBMITTED", "Files can be added only after the expert submits.", 409)
    if field.config.get("ops_upload", True) is not True:
        raise err("OPS_UPLOAD_BLOCKED", f"Admin has blocked uploads by Ops on '{field.label}'.",
                  403)


def attach(request, new: MediaAsset, replaces=None) -> None:
    """Ops put a file they uploaded into the submitted inspection: in place of `replaces` (kept as
    history, Admin can still open it) or added to the field. The report is rebuilt."""
    from apps.scoring import service as scoring

    user = request.user
    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=new.booking_id)
        new = MediaAsset.objects.select_for_update().get(pk=new.pk)
        field = field_for(booking, new.field_key)
        check_ops_upload(booking, field, user)
        if new.uploaded_by_id != user.pk or new.replaced_at is not None or new.status == "failed":
            raise err("UNKNOWN_MEDIA", "Upload the file first.")
        # half-sent: must not push out a good one
        if new.status not in ("uploaded", "verifying", "verified"):
            raise err("UPLOAD_NOT_FINISHED", "The file is still uploading.", 409)
        insp, part, ids = submitted_answer(booking, field, lock=True)
        answers = dict(insp.answers.get(part) or {})
        if str(new.id) in ids:
            return                                           # a retry: already in place
        old = None
        # an Ops "add" to a full field takes the place of a file that never arrived (a lost
        # phone), so the job can be finished; with room left it is simply added
        if replaces is None and len(ids) >= max_count(field):
            replaces = first_unarrived(booking, ids)
        if replaces is not None:
            old = live_asset(booking, field.key, replaces)
            if old is None or str(old.id) not in ids:
                raise err("UNKNOWN_MEDIA", "The file to replace is not on this field.")
            ids[ids.index(str(old.id))] = str(new.id)
        else:
            limit = max_count(field)
            if len(ids) >= limit:
                raise err("TOO_MANY",
                          f"'{field.label}' takes at most {limit}. Replace one instead.", 409)
            ids.append(str(new.id))
        answers[field.key] = ids
        insp.answers = {**insp.answers, part: answers}
        stamp(insp, user, [field.key])
        insp.save()
        if old is not None:
            old.replaced_by, old.replaced_at = new, timezone.now()
            old.save(update_fields=["replaced_by", "replaced_at"])
        scoring.recompute(insp)
        drop_zips(MediaZip.objects.filter(booking=booking))      # cached ZIPs no longer match
        activity.log(booking, user, "media_replaced" if old else "media_added",
                     {"media": [str(old.id) if old else None, str(new.id)]},
                     keys=[f"{part}.{field.key}"], inspection=insp)
        events.emit("inspection.updated", booking=str(booking.id), inspection=str(insp.id),
                    keys=[field.key])                     # the report is made again (handlers)
    check_completion(booking.id)     # a submitted booking now also waits for this file


def remove(request, asset: MediaAsset) -> None:
    """Nobody deletes a submitted file (Ops replace it instead). Anyone may only take back a file
    they uploaded themselves that no submitted inspection uses yet (the expert's Remove button, an
    Ops upload that was never attached), so a retake is never blocked by an unwanted file."""
    user = request.user
    booking = asset.booking
    # named by a submitted inspection's file fields (not just any text that quotes the id)
    used = any(str(asset.id) in expected_media(i) for i in booking.inspections.filter(
        status="submitted"))
    mine_unused = asset.uploaded_by_id == user.pk and not used and asset.replaced_at is None
    if not mine_unused or (booking.stage in ("completed", "cancelled")
                           and not is_manager(user, request)):
        raise err("DELETE_NOT_ALLOWED", "You can only take back your own file before it is "
                  "submitted.", 403)
    delete_asset(user, asset)


def delete_asset(actor, asset: MediaAsset) -> None:
    """Ops remove a file after submission: the object, its preview, its reference in the answers."""
    from apps.scoring import service as scoring

    with transaction.atomic():
        for insp in asset.booking.inspections.select_for_update().all():
            changed = False
            for part in PARTS:
                answers = dict(insp.answers.get(part) or {})
                for key, value in answers.items():
                    if value == str(asset.id):
                        answers[key] = None
                        changed = True
                    elif isinstance(value, list) and str(asset.id) in value:
                        answers[key] = [v for v in value if v != str(asset.id)]
                        changed = True
                if changed:
                    insp.answers = {**insp.answers, part: {k: v for k, v in answers.items()
                                                           if v not in (None, [])}}
            if changed:
                stamp(insp, actor, [asset.field_key])
                insp.save()
                scoring.recompute(insp)
        drop_zips(MediaZip.objects.filter(booking=asset.booking))  # cached ZIPs no longer match
        keys = asset_keys(asset)
        upload = asset.upload_id
        asset.delete()

        def clean_storage():                  # only once the database change is really saved
            for key in keys:
                storage.delete(key)
            if upload:
                storage.abort_multipart(asset.key, upload)

        core_tasks.after_commit(clean_storage)
    events.emit("media.deleted", booking=str(asset.booking_id), field_key=asset.field_key)
    check_completion(asset.booking_id)        # the removed file may have been the one holding it up
