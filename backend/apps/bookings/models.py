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
    chassis_no = models.CharField(max_length=64, blank=True)  # from the submitted inspection
    inspection_date = models.DateField(null=True, blank=True)
    row_version = models.PositiveIntegerField(default=0)
    last_change = models.JSONField(default=dict)   # {"by": username, "at": iso, "keys": [...]}
    last_edited_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                       on_delete=models.PROTECT, related_name="+")
    last_edited_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    # server-clock minutes, stamped at Start / Submit (see timing.py); compared to the settings
    late_minutes = models.IntegerField(null=True, blank=True)       # started after the booked time
    duration_minutes = models.IntegerField(null=True, blank=True)   # Start -> Submit
    # who looked at each flag, and when (two different problems, reviewed apart)
    late_reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                         on_delete=models.PROTECT, related_name="+")
    late_reviewed_at = models.DateTimeField(null=True, blank=True)
    quick_reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                          on_delete=models.PROTECT, related_name="+")
    quick_reviewed_at = models.DateTimeField(null=True, blank=True)
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
    # the start / end forms this inspection goes through, frozen at start (null: not used)
    start_version = models.ForeignKey("forms.FormVersion", null=True, blank=True,
                                      on_delete=models.PROTECT, related_name="+")
    end_version = models.ForeignKey("forms.FormVersion", null=True, blank=True,
                                    on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=10, default="draft")  # draft | submitted
    # {"inspection": {...}, "start": {...}, "end": {...}} (cleaned)
    answers = models.JSONField(default=dict)
    scores = models.JSONField(default=dict)     # computed: Key Checks, ratings, overall
    overrides = models.JSONField(default=dict)  # Ops overrides: ratings, derived, overall
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

    def pinned(self) -> dict:
        """part -> the form version this inspection was started on (None: part not used)."""
        return {"inspection": self.form_version, "start": self.start_version,
                "end": self.end_version}


class BookingActivity(models.Model):
    """What happened to a booking, for its timeline and the "edited by Ops" filter.
    Append-only. Values are kept only for schedule / stage / assignment keys; other changes
    keep just the field keys (answers can be sensitive and are visible per role)."""

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="activity")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                              on_delete=models.PROTECT, related_name="+")  # null: the system
    # created | changed | edited | inspection_edited | ratings_changed
    kind = models.CharField(max_length=24)
    changes = models.JSONField(default=dict)   # {key: [old, new]} for SAFE_KEYS only
    keys = models.JSONField(default=list)      # every changed key ("part.key" for inspections)
    inspection = models.ForeignKey(Inspection, null=True, blank=True, on_delete=models.CASCADE,
                                   related_name="+")
    at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-at", "-id"]
