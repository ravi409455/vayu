"""The forms app: after every migrate the booking, start and end forms exist."""
from django.apps import AppConfig
from django.db import DatabaseError, transaction
from django.db.models.signals import post_migrate


def _ensure_system_forms(sender, **kwargs):
    """After every migrate (and after a test database is flushed): the booking, start and end forms
    always exist."""
    from .services import ensure_system_forms

    try:
        with transaction.atomic():
            ensure_system_forms()
    except DatabaseError:        # migrating to an older point: the tables are not there yet
        pass


class FormsConfig(AppConfig):
    name = "apps.forms"

    def ready(self):
        post_migrate.connect(_ensure_system_forms, sender=self, dispatch_uid="ensure_system_forms")
