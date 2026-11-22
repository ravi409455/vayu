from rest_framework.exceptions import APIException


class CodedError(APIException):
    """API error with a machine-readable code: {"code": ..., "detail": ...}."""

    def __init__(self, code: str, detail: str, status_code: int):
        self.status_code = status_code
        super().__init__({"code": code, "detail": detail})
