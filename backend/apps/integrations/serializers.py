"""Integration request bodies (Q2.5): IntegrationSerializer checks and cleans what the Admin's
webhook editor sends, so the views only parse, call it and shape the reply."""
from typing import Any

from rest_framework import serializers

from apps.core.errors import fail
from apps.forms.models import Form

from . import values, webhooks
from .models import Integration

TOGGLES = ("include_data", "include_pdf", "include_image_zip", "include_video_zip", "is_active")
DESIGN = ("form", "event", "url", "query", "headers", "body_mode", "body")   # need a fresh check
MAX_TEXT = 1000


def _text(value: Any, what: str, allowed: set[str], *, one_line: bool = False) -> str:
    """A string that may hold {{ref}} tokens; every token must be one the form offers."""
    if not isinstance(value, str) or len(value) > MAX_TEXT:
        raise fail("INVALID_VALUE", f"{what} must be text of up to {MAX_TEXT} characters.")
    if not values.check_syntax(value):
        raise fail("INVALID_VALUE", f"{what} has a '{{{{' or '}}}}' that is not a whole value.")
    if one_line and ("\r" in value or "\n" in value):
        raise fail("INVALID_VALUE", f"{what} cannot hold a line break.")
    bad = [r for r in values.refs_in(value) if r not in allowed]
    if bad:
        raise fail("UNKNOWN_VALUE", f"{what} uses {bad[0]}, which this form and event do not "
                   "offer.", ref=bad[0])
    return value


def _json(node: Any, allowed: set[str], depth: int, count: list[Any]) -> Any:
    """A custom body: any JSON object or list; strings may hold {{ref}} values the form offers."""
    count[0] += 1
    if count[0] > values.MAX_NODES or depth > values.MAX_DEPTH:
        raise fail("INVALID_BODY", f"The body is too big or nested too deeply (up to "
                   f"{values.MAX_NODES} values, {values.MAX_DEPTH} levels).")
    if isinstance(node, str):
        return _text(node, "A body value", allowed)
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if not k.strip() or len(k) > 100 or "{{" in k:
                raise fail("INVALID_BODY", "A name in the body is plain text of up to 100 "
                           "characters.")
            out[k] = _json(v, allowed, depth + 1, count)
        return out
    if isinstance(node, list):
        return [_json(v, allowed, depth + 1, count) for v in node]
    if node is None or isinstance(node, (bool, int, float)):
        return node
    raise fail("INVALID_BODY", "The body is JSON.")           # pragma: no cover - JSON has no more


def clean_integration(data: dict[str, Any], current: Integration | None = None, *,
                       check_address: bool = True) -> dict[str, Any]:
    """Validated column values from a request body (only what the body carries)."""
    out: dict[str, Any] = {}
    if "form" in data or current is None:
        form_id = data.get("form")
        chosen = Form.objects.filter(pk=form_id).first() if isinstance(form_id, int) else None
        if chosen is None or chosen.type not in webhooks.EVENTS_FOR:
            raise fail("INVALID_FORM", "Choose the booking form, an inspection form or the "
                       "Check-in form.")
        out["form"] = chosen
    if "name" in data or current is None:
        name = data.get("name")
        if not isinstance(name, str) or not name.strip() or len(name) > 100:
            raise fail("INVALID_NAME", "Give the integration a name (up to 100 characters).")
        out["name"] = name.strip()
    if "event" in data or current is None:
        if data.get("event") not in webhooks.EVENTS:
            raise fail("INVALID_EVENT", "Pick one event.", allowed=webhooks.EVENTS)
        out["event"] = data["event"]
    form: Form = out["form"] if "form" in out else current.form        # type: ignore[union-attr]
    event = out.get("event") or (current.event if current else "")
    if event not in webhooks.EVENTS_FOR[form.type]:
        raise fail("INVALID_EVENT", "This form cannot use that event.",
                   allowed=webhooks.EVENTS_FOR[form.type])
    if "method" in data or current is None:
        method = data.get("method", "POST")
        if method not in webhooks.METHODS:
            raise fail("INVALID_METHOD", "Pick POST, PUT, PATCH, GET or DELETE.",
                       allowed=webhooks.METHODS)
        out["method"] = method
    for key in TOGGLES:
        if key in data:
            if not isinstance(data[key], bool):
                raise fail("INVALID_TOGGLE", f"{key} must be true or false.")
            out[key] = data[key]
    if "fields" in data:
        fields = data["fields"]
        if not isinstance(fields, list) or not all(isinstance(f, str) for f in fields):
            raise fail("INVALID_FIELDS", "fields must be a list of field keys.")
        out["fields"] = sorted(set(fields))
    if "body_mode" in data and data["body_mode"] not in ("standard", "custom"):
        raise fail("INVALID_BODY", "The body is standard or custom.")
    if not any(k in data for k in DESIGN) and current is not None:
        return out                                   # a toggle or a rename: nothing to re-check
    allowed = {e["ref"] for e in values.catalogue(form, event)}
    url = data["url"] if "url" in data or current is None else current.url
    if not isinstance(url, str) or len(url) > 500 or not url.startswith(("http://", "https://")):
        raise fail("INVALID_URL", "This URL cannot be used (bad_url).", reason="bad_url")
    base = "/".join(url.split("/", 3)[:3])
    after = url[len(base):]
    if "{{" in base or any("{{" in part for part in after.replace("#", "?").split("?")[1:]):
        raise fail("INVALID_URL", "Values can go in the path only, not in the address or the "
                   "query (use the query rows).", reason="value_outside_path")
    _text(url, "The URL", allowed)
    if check_address:
        reason = webhooks.check_url(values.TOKEN.sub("x", url))
        if reason:
            raise fail("INVALID_URL", f"This URL cannot be used ({reason}).", reason=reason)
    out["url"] = url
    query = data.get("query", current.query if current else [])
    if (not isinstance(query, list) or len(query) > values.MAX_QUERY
            or not all(isinstance(q, dict) for q in query)):
        raise fail("INVALID_QUERY", f"Query parameters are a list of up to {values.MAX_QUERY}.")
    out["query"] = []
    for q in query:
        key = q.get("key")
        if not isinstance(key, str) or not key.strip() or len(key) > 100 or "{{" in key:
            raise fail("INVALID_QUERY", "A query parameter needs a plain name.")
        out["query"].append({"key": key.strip(),
                             "value": _text(q.get("value", ""), f"Query '{key}'", allowed)})
    headers = data.get("headers", current.headers if current else [])
    if (not isinstance(headers, list) or len(headers) > values.MAX_HEADERS
            or not all(isinstance(h, dict) for h in headers)):
        raise fail("INVALID_HEADERS", f"Headers are a list of up to {values.MAX_HEADERS}.")
    out["headers"], names = [], set()
    for h in headers:
        name = h.get("key")
        if not isinstance(name, str) or not webhooks.HEADER_NAME.fullmatch(name) or len(name) > 100:
            raise fail("INVALID_HEADERS", "A header name is letters, digits and - only.")
        if name.lower() in webhooks.LOCKED_HEADERS or name.lower().startswith("x-vayu-"):
            raise fail("LOCKED_HEADER", f"{name} is set by the system and cannot be changed.")
        if name.lower() in names:
            raise fail("INVALID_HEADERS", f"{name} is listed twice.")
        names.add(name.lower())
        out["headers"].append({"key": name, "value": _text(h.get("value", ""), f"Header {name}",
                                                          allowed, one_line=True)})
    mode = out.get("body_mode") or data.get("body_mode") or (current.body_mode if current
                                                             else "standard")
    out["body_mode"] = mode
    body = data.get("body", current.body if current else {})
    if mode == "custom":
        if not isinstance(body, (dict, list)):
            raise fail("INVALID_BODY", "The body is a JSON object or list.")
        out["body"] = _json(body, allowed, 1, [0])
    else:
        out["body"] = {}
    return out



class IntegrationSerializer(serializers.BaseSerializer[Integration]):
    """Validated column values from a body: everything for a new integration ([instance] None),
    only what the body carries for a change. [check_address]: False skips the URL's DNS check
    (a preview). Errors are coded (INVALID_URL, UNKNOWN_VALUE, …), not DRF field errors."""

    def __init__(self, instance: Integration | None = None, *, check_address: bool = True,
                 **kwargs: Any) -> None:
        super().__init__(instance, **kwargs)
        self.check_address = check_address

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        return clean_integration(data, self.instance, check_address=self.check_address)
