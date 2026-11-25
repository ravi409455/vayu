import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

KINDS = ("photo", "video", "file", "signature")


class MediaStatus(models.TextChoices):
    """Where an upload is (F-008); compares equal to its plain string."""
    PENDING = "pending"            # registered, parts on their way
    UPLOADED = "uploaded"          # every part arrived, not checked yet
    VERIFYING = "verifying"        # a check is running
    VERIFIED = "verified"
    FAILED = "failed"              # checksum, not a picture / video: the phone sends it again
    PURGED = "purged"              # removed by the retention setting


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
    status = models.CharField(max_length=10, choices=MediaStatus.choices,
                              default=MediaStatus.PENDING)
    key = models.CharField(max_length=200)
    preview_key = models.CharField(max_length=200, blank=True)
    # a JPEG copy (at most 2048 px) for the PDF when the original is HEIC or bigger; the
    # original is never rewritten
    jpeg_key = models.CharField(max_length=200, blank=True)
    upload_id = models.TextField(blank=True)   # R2 ids are ~343 characters
    stuck_alerted = models.BooleanField(default=False)
    # how many times it failed verification before (a retry reuses the row, F-247)
    failed_attempts = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    verified_at = models.DateTimeField(null=True, blank=True)
    # Ops swapped this file for another: kept as history, out of the answers, ZIPs and limits
    replaced_by = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    replaced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        # the stuck-upload list and the hourly purge (F-091)
        indexes = [models.Index(fields=["status", "created_at"], name="media_status_created"),
                   models.Index(fields=["kind", "status", "created_at"],
                                name="media_kind_status_created")]


class MediaZip(models.Model):
    """A cached ZIP of a booking's media (images or videos)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey("bookings.Booking", on_delete=models.CASCADE,
                                related_name="zips")
    kind = models.CharField(max_length=10)             # image | video
    excluded = models.JSONField(default=list)          # field keys left out (hidden from them)
    # asset ids it may hold, empty = any (the customer's links: only the counted inspection's)
    only = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=10, default="building")  # building | ready | failed
    progress = models.PositiveSmallIntegerField(default=0)
    key = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    built_at = models.DateTimeField(null=True, blank=True)
