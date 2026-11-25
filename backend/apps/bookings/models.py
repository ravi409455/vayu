"""Bookings, their reschedule history, the inspections experts submit, and the activity timeline."""
import uuid

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from .stages import STAGES, InspectionStatus


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
    last_change = models.JSONField(default=dict)   # {"by": shown name, "at": iso, "keys": [...]}
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
    # an inspection on it was done while the phone's clock was not checked (F-222)
    unverified_time = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT,
                                   related_name="+")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(Lower("booking_id"), name="booking_id_ci_unique")]
        ordering = ["-created_at"]
        # the list filters (Today, Bookings) (R-17); search by trigram index when it slows
        indexes = [models.Index(fields=["stage", "inspection_date"], name="booking_stage_date"),
                   models.Index(fields=["city"], name="booking_city"),
                   models.Index(fields=["inspection_type"], name="booking_type"),
                   models.Index(fields=["assigned_expert", "inspection_date"],
                                name="booking_expert_date")]

    def counted_inspection(self) -> "Inspection | None":
        """The inspection that counts: what the report, its ZIPs, webhooks and the external API
        use. Normally the newest submitted one. During a conflict, the one that counted before it
        arrived (the earlier), so the customer keeps the old report; none when the conflict came
        with the first submission (no report until Ops choose)."""
        done = list(self.inspections.filter(status="submitted").order_by("submitted_at"))
        if self.conflict:
            return done[0] if len(done) > 1 else None
        return done[-1] if done else None


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
    status = models.CharField(max_length=10, choices=InspectionStatus.choices,
                              default=InspectionStatus.DRAFT)
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
    # the phone's clock was not checked against the server at some point (true wins, F-222)
    unverified_time = models.BooleanField(default=False)
    client_start_uuid = models.UUIDField(null=True, blank=True, unique=True)
    client_submission_uuid = models.UUIDField(null=True, blank=True, unique=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at"]
        constraints = [models.UniqueConstraint(fields=["booking", "expert"],
                                               condition=models.Q(status="draft"),
                                               name="one_open_draft_per_expert")]

    def pinned(self) -> dict:
        """part -> the form version this inspection was started on (None: part not used)."""
        return {"inspection": self.form_version, "start": self.start_version,
                "end": self.end_version}


class BookingActivity(models.Model):
    """What happened to a booking, for its timeline and the "edited by Ops" filter.
    Append-only. Values are kept only for schedule / stage / assignment keys; other changes
    keep just the field keys (answers can be sensitive and are visible per role)."""

    # kept when the booking is deleted, for metrics (F-247): then only booking_ref names it
    booking = models.ForeignKey(Booking, null=True, on_delete=models.SET_NULL,
                                related_name="activity")
    booking_ref = models.CharField(max_length=64, blank=True)    # the Booking ID as it was
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                              on_delete=models.PROTECT, related_name="+")  # null: the system
    # created | changed | edited | inspection_edited | ratings_changed
    kind = models.CharField(max_length=24)
    changes = models.JSONField(default=dict)   # {key: [old, new]} for SAFE_KEYS only
    keys = models.JSONField(default=list)      # every changed key ("part.key" for inspections)
    inspection = models.ForeignKey(Inspection, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-at", "-id"]
