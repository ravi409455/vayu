"""What the backend sends to Sentry: the error and where it happened, never customer data (H-03).
No request bodies, no local variables (they hold answers, names, phone numbers), no query strings
(search terms), cookies or headers (tokens)."""
from typing import Any


def scrub(event: dict, hint=None) -> dict:
    request = event.get("request")
    if isinstance(request, dict):
        event["request"] = {k: v for k, v in request.items() if k in ("method", "url")}
        if isinstance(event["request"].get("url"), str):
            event["request"]["url"] = event["request"]["url"].split("?")[0]
    for value in (event.get("exception") or {}).get("values") or []:
        for frame in (value.get("stacktrace") or {}).get("frames") or []:
            frame.pop("vars", None)
    return event


OPTIONS: dict[str, Any] = {"send_default_pii": False, "include_local_variables": False,
                           "max_request_body_size": "never", "before_send": scrub}
