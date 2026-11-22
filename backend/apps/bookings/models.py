import uuid

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from .stages import STAGES


class Booking(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)  # internal ID
    booking_id = models.CharField(max_length=64)  # the ID Ops type; editable, unique ignoring case
    stage = models.CharField(max_length=12, choices=[(s, s) for s in STAGES], default="draft")
    ops_status = models.CharField(max_length=64, blank=True)
    inspection_type = models.CharField(max_length=64, blank=True)
    assigned_expert = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                        on_delete=models.PROTECT, related_name="assigned_bookings")
    answers = models.JSONField(default=dict)       # booking form answers (cleaned)
    # copies of locked system fields, for search, filters and dashboards
    customer_name = models.CharField(max_length=200, blank=True)
    customer_phone = models.CharField(max_length=20, blank=True)
    city = models.CharField(max_length=64, blank=True)
    car_make_model = models.CharField(max_length=64, blank=True)
    inspection_date = models.DateField(null=True, blank=True)
    row_version = models.PositiveIntegerField(default=0)
    last_change = models.JSONField(default=dict)   # {"by": username, "at": iso, "keys": [...]}
    last_edited_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                       on_delete=models.PROTECT, related_name="+")
    last_edited_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    released_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.PROTECT, related_name="+")
    released_at = models.DateTimeField(null=True, blank=True)
    released_draft_expected = models.BooleanField(default=False)
    cancel_reason = models.CharField(max_length=64, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    conflict = models.CharField(max_length=40, blank=True)  # TWO_EXPERTS, RELEASED_DRAFT_ARRIVED
    withdrawn_expert = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                         on_delete=models.PROTECT, related_name="+")
    alerts = models.JSONField(default=list)        # [{"code": ..., "at": ..., "detail": ...}]
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT,
                                   related_name="+")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(Lower("booking_id"), name="booking_id_ci_unique")]
        ordering = ["-created_at"]


class RescheduleLog(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="reschedules")
    old_date = models.CharField(max_length=10)
    old_time = models.CharField(max_length=5)
    new_date = models.CharField(max_length=10)
    new_time = models.CharField(max_length=5)
    reason = models.CharField(max_length=64)
    by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["at", "id"]


class Inspection(models.Model):
    """One expert's inspection of a booking. A booking can have several only in a conflict
    (two experts); Ops then choose which one counts."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="inspections")
    expert = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                               related_name="inspections")
    form_version = models.ForeignKey("forms.FormVersion", on_delete=models.PROTECT,
                                     related_name="+")  # frozen at start
    status = models.CharField(max_length=10, default="draft")  # draft | submitted
    answers = models.JSONField(default=dict)    # {"inspection": {...}, "ops": {...}} (cleaned)
    row_version = models.PositiveIntegerField(default=0)
    last_change = models.JSONField(default=dict)
    last_edited_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                       on_delete=models.PROTECT, related_name="+")
    last_edited_at = models.DateTimeField(null=True, blank=True)
    client_started_at = models.DateTimeField(null=True, blank=True)
    client_start_uuid = models.UUIDField(null=True, blank=True, unique=True)
    client_submission_uuid = models.UUIDField(null=True, blank=True, unique=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at"]
