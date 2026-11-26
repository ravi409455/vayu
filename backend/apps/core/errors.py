"""The coded API error (CodedError) and fail(), the one way to raise one."""
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
        self.code, self.payload = code, payload


def fail(code: str, message: str, status: int = 400, **extra: Any) -> CodedError:
    """Makes a coded API error (the same as `CodedError(...)`, which older code still calls
    directly; both are read by the error-code table), e.g.
    `raise fail("STALE_BOOKING", "Someone changed this booking.", 409, row_version=3)`.
    The code must be listed in docs/error-codes.md (a test checks)."""
    return CodedError(code, message, status, **extra)
