from typing import Any

from rest_framework.exceptions import APIException


class CodedError(APIException):
    """API error with a machine-readable code: {"code": ..., "detail": ..., **extra}.

    DRF stringifies every value of an exception's detail; the payload is kept as plain JSON so
    numbers, lists and objects (row_version, issues, errors) reach clients with their types."""

    def __init__(self, code: str, detail: str, status_code: int, **extra: Any) -> None:
        self.status_code = status_code
        payload = {"code": code, "detail": detail, **extra}
        super().__init__(payload)
        self.detail = payload
