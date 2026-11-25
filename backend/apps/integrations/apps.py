"""The integrations app: webhooks subscribe to domain events on start."""
from django.apps import AppConfig


class IntegrationsConfig(AppConfig):
    name = "apps.integrations"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.core import events

        from . import webhooks

        events.subscribe(webhooks.on_event)
