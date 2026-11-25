"""Bell notifications and Android app releases."""
from django.conf import settings
from django.db import models
from django.utils import timezone


class Notification(models.Model):
    """One line in a person's bell list. The same row is what a push shows."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="notifications")
    kind = models.CharField(max_length=20)
    title = models.CharField(max_length=200)
    body = models.CharField(max_length=300, blank=True)
    booking = models.ForeignKey("bookings.Booking", null=True, blank=True,
                                on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(default=timezone.now)
    read_at = models.DateTimeField(null=True, blank=True)
    # push outcome, for metrics (F-247): phones reached, and dead tokens dropped
    pushed = models.PositiveSmallIntegerField(default=0)
    push_failed = models.PositiveSmallIntegerField(default=0)

    class Meta:
        indexes = [models.Index(fields=["user", "-created_at"])]


class AppRelease(models.Model):
    """One Android build people can install. The newest row is what "Update available" offers;
    the file lives in the file store (see the publish_apk command)."""

    version_code = models.PositiveIntegerField(unique=True)
    version_name = models.CharField(max_length=40)
    file_key = models.CharField(max_length=300)
    size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    notes = models.TextField(blank=True)               # one change per line
    created_at = models.DateTimeField(default=timezone.now)
