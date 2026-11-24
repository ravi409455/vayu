import secrets

from django.db import models
from django.db.models import Q
from django.utils import timezone


class PdfTemplate(models.Model):
    """One report layout per inspection form."""

    form = models.OneToOneField("forms.Form", on_delete=models.CASCADE,
                                related_name="pdf_template")
    created_at = models.DateTimeField(default=timezone.now)


class PdfTemplateVersion(models.Model):
    template = models.ForeignKey(PdfTemplate, on_delete=models.CASCADE, related_name="versions")
    number = models.PositiveIntegerField()
    status = models.CharField(max_length=10, default="draft")   # draft | published
    definition = models.JSONField(default=dict)
    row_version = models.PositiveIntegerField(default=0)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["template", "number"], name="pdf_version_number"),
            models.UniqueConstraint(fields=["template"], condition=Q(status="draft"),
                                    name="one_pdf_draft_per_template"),
        ]


class SharedItem(models.Model):
    """A theme (colours, fonts, header and footer, watermark) or a shared part (e.g. the
    disclaimer) that many templates use. Each save is a new revision; templates name the
    revision they use, so a report always shows what it was made with."""

    kind = models.CharField(max_length=10)                        # theme | snippet
    key = models.CharField(max_length=63)
    name = models.CharField(max_length=100)
    revision = models.PositiveIntegerField(default=0)             # the newest
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["kind", "key"], name="shared_kind_key")]


class SharedRevision(models.Model):
    item = models.ForeignKey(SharedItem, on_delete=models.CASCADE, related_name="revisions")
    revision = models.PositiveIntegerField()
    content = models.JSONField()
    created_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["item", "revision"],
                                               name="shared_revision_number")]


def new_token() -> str:
    return secrets.token_urlsafe(24)      # 192 bits: unguessable, stable across revisions


class Report(models.Model):
    """The latest PDF of a booking. Older revisions are not kept."""

    booking = models.OneToOneField("bookings.Booking", on_delete=models.CASCADE,
                                   related_name="report")
    token = models.CharField(max_length=64, unique=True, default=new_token)
    revision = models.PositiveIntegerField(default=0)
    # pending | ready (a PDF exists, even if a later render failed: see error) | failed (none yet)
    status = models.CharField(max_length=10, default="pending")
    key = models.CharField(max_length=200, blank=True)
    filename = models.CharField(max_length=200, blank=True)
    template_version = models.ForeignKey(PdfTemplateVersion, null=True, blank=True,
                                         on_delete=models.SET_NULL, related_name="+")
    stale = models.BooleanField(default=False)    # data changed since this PDF was made
    error = models.TextField(blank=True)
    generated_at = models.DateTimeField(null=True, blank=True)
    # the booking's first PDF: the photo / video ZIP links in it last 30 days from then (R-09)
    first_generated_at = models.DateTimeField(null=True, blank=True)
    render_started_at = models.DateTimeField(null=True, blank=True)   # set while a render runs
    retry_at = models.DateTimeField(null=True, blank=True)    # failed: tried again from then
