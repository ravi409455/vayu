import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Integration(models.Model):
    """One webhook of one form: one event, one request (method, URL, query, headers, body)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    form = models.ForeignKey("forms.Form", on_delete=models.CASCADE, related_name="integrations")
    name = models.CharField(max_length=100)
    event = models.CharField(max_length=40)
    method = models.CharField(max_length=6, default="POST")
    url = models.CharField(max_length=500)         # may hold {{ref}} after the host
    query = models.JSONField(default=list)         # [{"key": "src", "value": "{{job.city}}"}]
    headers = models.JSONField(default=list)       # [{"key": "X-Token", "value": "abc"}]
    body_mode = models.CharField(max_length=10, default="standard")   # standard | custom
    body = models.JSONField(default=dict)          # custom: {"rows": [...]}, see values.build_tree
    include_data = models.BooleanField(default=True)
    include_pdf = models.BooleanField(default=False)
    include_image_zip = models.BooleanField(default=False)
    include_video_zip = models.BooleanField(default=False)
    fields = models.JSONField(default=list)        # standard body: field keys that may leave
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                   on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]


class Delivery(models.Model):
    """One attempt series to one URL for one event. Metadata only: no payload is ever stored,
    the body is built again from current data when it is sent."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    integration = models.ForeignKey(Integration, on_delete=models.CASCADE,
                                    related_name="deliveries")
    event = models.CharField(max_length=40)
    booking = models.ForeignKey("bookings.Booking", null=True, on_delete=models.SET_NULL,
                                related_name="+")
    booking_uuid = models.CharField(max_length=36, blank=True)
    booking_ref = models.CharField(max_length=64, blank=True)
    context = models.JSONField(default=dict)       # small facts: changed keys, ids, alert code
    status = models.CharField(max_length=10, default="pending")
    # pending | sending | retrying | success | failed
    attempts = models.PositiveSmallIntegerField(default=0)
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    error = models.CharField(max_length=40, blank=True)    # reason code only
    next_retry_at = models.DateTimeField(null=True, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    resent_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="+")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "next_retry_at"])]


class ApiKey(models.Model):
    """Lets another system call the REST API. Only the SHA-256 of the key is stored."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    prefix = models.CharField(max_length=12, unique=True)   # visible, finds the key
    key_hash = models.CharField(max_length=64)
    # {"forms": {"<form key>": ["field", ...] | ["*"]}}: what the key may read and write
    scope = models.JSONField(default=dict)
    allow_delete = models.BooleanField(default=False)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                   on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
