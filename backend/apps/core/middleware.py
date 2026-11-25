"""Gives every request an id (the client's X-Request-ID if it is safe, else a new one), puts it in
the log lines and returns it in the response."""
import re
import uuid
from typing import Any

from rest_framework.request import Request

from .logging import request_id_var

_VALID_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")


class RequestIdMiddleware:
    def __init__(self, get_response: Any) -> None:
        self.get_response = get_response

    def __call__(self, request: Request) -> Any:
        rid = request.headers.get("X-Request-ID", "")
        if not _VALID_ID.fullmatch(rid):  # never reflect or log arbitrary client input
            rid = uuid.uuid4().hex
        token = request_id_var.set(rid)
        try:
            response = self.get_response(request)
        finally:
            request_id_var.reset(token)
        response["X-Request-ID"] = rid
        return response
