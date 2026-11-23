"""One place that turns "the client sent something odd" into a clean 400 instead of a 500."""
import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import DataError
from rest_framework.exceptions import ParseError
from rest_framework.parsers import JSONParser
from rest_framework.views import exception_handler

from .errors import CodedError

logger = logging.getLogger(__name__)
# PostgreSQL: 22001 string too long, 22003 number out of range, 22021 bad byte sequence (NUL),
# 22P02 bad text representation, 22007/22008 bad date/time
BAD_VALUE = {"22001", "22003", "22021", "22P02", "22007", "22008"}


def handler(exc, context):
    if isinstance(exc, DjangoValidationError):      # e.g. a malformed UUID in a lookup
        exc = CodedError("INVALID_INPUT", "; ".join(exc.messages), 400)
    elif isinstance(exc, DataError) and (
            getattr(exc.__cause__, "sqlstate", None) in BAD_VALUE or "NUL" in str(exc)):
        # a value the database cannot hold (too long, out of range, NUL byte) is the client's
        # doing - but it can also mean one of our columns is too small, so it is always logged
        # metadata only: the exception text can quote the customer's value
        logger.error("Database refused a value (sqlstate=%s, path=%s)",
                     getattr(exc.__cause__, "sqlstate", None),
                     getattr(context.get("request"), "path", "?"))
        exc = CodedError("INVALID_INPUT", "A value is not acceptable.", 400)
    return exception_handler(exc, context)


class ObjectJSONParser(JSONParser):
    """Every endpoint reads request.data like a dict; a top-level list or string is a 400."""

    def parse(self, stream, media_type=None, parser_context=None):
        data = super().parse(stream, media_type, parser_context)
        if not isinstance(data, dict):
            raise ParseError("The request body must be a JSON object.")
        return data
