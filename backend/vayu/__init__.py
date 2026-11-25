"""The Vayu Django project; importing it loads the Celery app."""
from .celery import app as celery_app

__all__ = ("celery_app",)
