"""The core app: on start it turns domain events into log events (apps.core.log)."""
from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "apps.core"

    def ready(self) -> None:
        from . import events, log

        events.subscribe(log.on_domain_event)
