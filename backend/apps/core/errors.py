from rest_framework.exceptions import APIException


class CodedError(APIException):
    """API error with a machine-readable code: {"code": ..., "detail": ..., **extra}."""

    def __init__(self, code: str, detail: str, status_code: int, **extra):
        self.status_code = status_code
        super().__init__({"code": code, "detail": detail, **extra})
