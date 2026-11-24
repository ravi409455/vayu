import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

KINDS = ("photo", "video", "file", "signature")


class MediaAsset(models.Model):
    """One uploaded photo/video/file/signature. The phone picks `client_uuid` so a retried
    request never creates a duplicate; the id is what form answers reference."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client_uuid = models.UUIDField(unique=True)
    booking = models.ForeignKey("bookings.Booking", on_delete=models.CASCADE,
                                related_name="media")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                    related_name="+")
    field_key = models.CharField(max_length=63)
    kind = models.CharField(max_length=10, choices=[(k, k) for k in KINDS])
    content_type = models.CharField(max_length=100)
    size = models.BigIntegerField()
    sha256 = models.CharField(max_length=64)
    source = models.CharField(max_length=10, default="camera")  # camera | gallery (internal only)
    status = models.CharField(max_length=10, default="pending")  # pending | verified
    key = models.CharField(max_length=200)
    preview_key = models.CharField(max_length=200, blank=True)
    upload_id = models.TextField(blank=True)   # R2 ids are ~343 characters
    stuck_alerted = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    verified_at = models.DateTimeField(null=True, blank=True)
    # Ops swapped this file for another: kept as history, out of the answers, ZIPs and limits
    replaced_by = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    replaced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]


class MediaZip(models.Model):
    """A cached ZIP of a booking's media (images or videos)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey("bookings.Booking", on_delete=models.CASCADE,
                                related_name="zips")
    kind = models.CharField(max_length=10)             # image | video
    excluded = models.JSONField(default=list)          # field keys left out (hidden from them)
    status = models.CharField(max_length=10, default="building")  # building | ready | failed
    progress = models.PositiveSmallIntegerField(default=0)
    key = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    built_at = models.DateTimeField(null=True, blank=True)
