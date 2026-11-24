from django.db import models


class Setting(models.Model):
    """One row per group of settings Admin can change (key "timing", ...); see app_settings.py."""

    key = models.CharField(max_length=64, primary_key=True)
    value = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)
