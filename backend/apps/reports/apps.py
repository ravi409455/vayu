"""The reports app: reports react to domain events on start (render, mark out of date)."""
from django.apps import AppConfig


class ReportsConfig(AppConfig):
    name = "apps.reports"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from apps.core import events

        from . import handlers

        events.subscribe(handlers.on_event)
