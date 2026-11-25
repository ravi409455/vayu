"""Every error code the API can answer with, read from the code (F-160): the table in
docs/error-codes.md is made from it, and a test keeps that table complete."""
import ast
from pathlib import Path

APPS = Path(__file__).resolve().parents[1]
CALLS = {"err", "CodedError", "bad"}        # the helpers that raise a coded error
# raised by DRF and the error handler (apps/core/exceptions.py), not by a call above
FRAMEWORK = {"INVALID": (400, "A field is invalid; `fields` says which."),
             "PARSE_ERROR": (400, "The body is not valid JSON (or not a JSON object)."),
             "NOT_AUTHENTICATED": (401, "Sign in first."),
             "AUTHENTICATION_FAILED": (401, "The token or key is not valid."),
             "PERMISSION_DENIED": (403, "Your role may not do this."),
             "NOT_FOUND": (404, "No such object (or not one you may see)."),
             "METHOD_NOT_ALLOWED": (405, "This endpoint does not take that method."),
             "THROTTLED": (429, "Too many requests; wait and try again.")}


def _text(node) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(str(v.value) if isinstance(v, ast.Constant) else "…" for v in node.values)
    if isinstance(node, ast.BinOp):
        return _text(node.left) + _text(node.right)
    return "…"


def codes() -> dict[str, tuple[int, str]]:
    """{code: (HTTP status, first message found)}."""
    out: dict[str, tuple[int, str]] = dict(FRAMEWORK)
    for path in sorted(APPS.rglob("*.py")):
        if "tests" in path.parts or "migrations" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if not (isinstance(node, ast.Call) and getattr(node.func, "id", "") in CALLS
                    and node.args and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                continue
            status = next((a.value for a in node.args[2:3] if isinstance(a, ast.Constant)
                           and isinstance(a.value, int)), 400)
            text = _text(node.args[1]) if len(node.args) > 1 else ""
            out.setdefault(node.args[0].value, (status, text))
    return out


def table() -> str:
    rows = ["| Code | HTTP | Meaning |", "|---|---|---|"]
    rows += [f"| `{c}` | {s} | {m.replace('|', '/')} |" for c, (s, m) in sorted(codes().items())]
    return "\n".join(rows)


ERROR_SCHEMA = {"type": "object", "required": ["code", "detail"], "properties": {
    "code": {"type": "string", "description": "Stable; see docs/error-codes.md."},
    "detail": {"type": "string"},
    "fields": {"type": "object", "additionalProperties": {"type": "array", "items": {}}},
    "errors": {"type": "object", "additionalProperties": {"type": "string"}},
    "messages": {"type": "object", "additionalProperties": {"type": "string"}}},
    "additionalProperties": True}
ERROR_STATUSES = {"400": "Invalid request", "401": "Not signed in", "403": "Not allowed",
                  "404": "Not found", "409": "Conflict with the current state"}


def add_error_responses(result, generator, request, public):
    """drf-spectacular hook (F-161): every operation documents the one error body."""
    result.setdefault("components", {}).setdefault("schemas", {})["Error"] = ERROR_SCHEMA
    ref = {"$ref": "#/components/schemas/Error"}
    for path in result.get("paths", {}).values():
        for op in path.values():
            responses = op.setdefault("responses", {})
            for status, words in ERROR_STATUSES.items():
                responses.setdefault(status, {"description": words,
                                              "content": {"application/json": {"schema": ref}}})
    return result
