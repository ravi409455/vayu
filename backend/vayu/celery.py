"""The Celery app, and the signals that carry a request's id into the jobs it queues."""
import os

from celery import Celery
from celery.signals import before_task_publish, task_prerun

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "vayu.settings.prod")
app = Celery("vayu")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


# a task logs with the request id of the API call that queued it, so one booking's story can be
# followed from the request to the worker (F-212)
@before_task_publish.connect
def _carry_request_id(headers=None, **_):
    from apps.core.logging import request_id_var

    if headers is not None:
        headers.setdefault("request_id", request_id_var.get())


@task_prerun.connect
def _restore_request_id(task=None, task_id=None, **_):
    from apps.core.logging import request_id_var, task_id_var

    request_id_var.set(getattr(task.request, "request_id", None) or "-")
    task_id_var.set(task_id or "-")                     # and every line says which task (Q4.2)
