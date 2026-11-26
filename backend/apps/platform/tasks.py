"""The "workers alive" heartbeat (docs/plan-deploy.md 1.15)."""
import logging

import requests
from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(ignore_result=True)
def heartbeat() -> None:
    """Queued by beat every 5 minutes, run by a worker: one ping proves beat, Redis and a worker."""
    if not settings.WORKERS_HEARTBEAT_URL:
        return
    try:
        requests.get(settings.WORKERS_HEARTBEAT_URL, timeout=10)
    except requests.RequestException:
        logger.warning("heartbeat ping failed")   # the checker alerts on the missing ping
