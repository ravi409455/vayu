"""Request and task ids for log lines (set by the middleware and the Celery signals)."""
import logging
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
task_id_var: ContextVar[str] = ContextVar("task_id", default="-")    # set in a Celery worker


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.task_id = task_id_var.get()
        return True
