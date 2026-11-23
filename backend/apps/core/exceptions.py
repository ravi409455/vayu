"""One place that turns "the client sent something odd" into a clean 400 instead of a 500."""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import DataError
from rest_framework.exceptions import ParseError
from rest_framework.parsers import JSONParser
from rest_framework.views import exception_handler

from .errors import CodedError


def handler(exc, context):
    if isinstance(exc, DjangoValidationError):      # e.g. a malformed UUID in a lookup
        exc = CodedError("INVALID_INPUT", "; ".join(exc.messages), 400)
    elif isinstance(exc, DataError) and "NUL" in str(exc):   # a NUL byte in a text value
        exc = CodedError("INVALID_INPUT", "A value is not acceptable.", 400)
    # any other DataError is our bug (e.g. a column too small): let it surface as a 500
    return exception_handler(exc, context)


class ObjectJSONParser(JSONParser):
    """Every endpoint reads request.data like a dict; a top-level list or string is a 400."""

    def parse(self, stream, media_type=None, parser_context=None):
        data = super().parse(stream, media_type, parser_context)
        if not isinstance(data, dict):
            raise ParseError("The request body must be a JSON object.")
        return data
