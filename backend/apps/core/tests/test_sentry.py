"""H-03: what reaches Sentry never holds customer data."""
import sentry_sdk
from sentry_sdk.transport import Transport

from vayu.sentry_scrub import OPTIONS, scrub


def test_the_options_turn_off_bodies_locals_and_personal_data():
    assert OPTIONS["send_default_pii"] is False
    assert OPTIONS["include_local_variables"] is False
    assert OPTIONS["max_request_body_size"] == "never"


def test_a_real_error_event_leaves_no_answers_query_or_headers():
    sent: list = []

    class Keep(Transport):
        def capture_envelope(self, envelope):
            sent.extend(item.payload.json for item in envelope.items if item.payload.json)

    sentry_sdk.init(dsn="https://k@o0.ingest.sentry.io/1", transport=Keep, **OPTIONS)
    try:
        customer_phone = "98765" + "43210"           # a local variable that must not leave
        raise ValueError(f"boom {len(customer_phone)}")
    except ValueError:
        sentry_sdk.capture_exception()
    sentry_sdk.flush()
    sentry_sdk.init()                                 # off again for the other tests
    assert sent and "98765" + "43210" not in str(sent)        # no frame vars


def test_scrub_keeps_only_the_method_and_the_path():
    event = {"request": {"method": "POST", "url": "https://x/api/v1/bookings?search=Asha",
                         "data": {"customer_name": "Asha"}, "headers": {"Authorization": "t"},
                         "cookies": "s", "query_string": "search=Asha"},
             "exception": {"values": [{"stacktrace": {"frames": [{"vars": {"p": "98"}}]}}]}}
    out = scrub(event)
    assert out["request"] == {"method": "POST", "url": "https://x/api/v1/bookings"}
    assert out["exception"]["values"][0]["stacktrace"]["frames"] == [{}]
    assert scrub({"message": "x"}) == {"message": "x"}


def test_an_event_nobody_declared_is_refused():
    """F-044: one list of events; a typo never goes out silently."""
    import pytest

    from apps.core import events

    with pytest.raises(ValueError, match="Unknown event"):
        events.emit("booking.udpated", booking="x")


def test_core_is_the_bottom_layer_and_imports_no_other_app():
    """F-003: core (errors, events, tasks, settings, logging) is used by every app and uses none;
    setup, demo and test data live in apps.platform, on top. testing.py holds test fixtures."""
    import ast
    from pathlib import Path

    core = Path(__file__).resolve().parents[1]
    others = ("accounts", "bookings", "forms", "media", "reports", "integrations", "notify",
              "scoring", "platform")
    for path in core.rglob("*.py"):
        if "tests" in path.parts or "migrations" in path.parts or path.name == "testing.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            module = node.module if isinstance(node, ast.ImportFrom) else None
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else []
            for m in [module or "", *names]:
                assert not any(m.startswith(f"apps.{o}") for o in others), (path.name, m)


def test_every_error_body_has_a_code_and_a_detail(api_as):
    """F-160: one shape whoever raised the error; field errors keep their keys."""
    ops, _ = api_as("ops")
    timing = ops.get("/api/v1/bookings?timing=x").json()
    assert timing["code"] == "INVALID" and timing["detail"] == "Use late or quick."
    assert timing["fields"] == {"timing": ["Use late or quick."]} and timing["timing"]
    missing = ops.get("/api/v1/bookings/00000000-0000-0000-0000-000000000000").json()
    assert missing["code"] == "NOT_FOUND" and missing["detail"]
    coded = ops.get("/api/v1/sync/jobs?have=x")
    assert coded.json()["code"] in ("INVALID_QUERY", "PERMISSION_DENIED")
    from rest_framework.test import APIClient

    anon = APIClient().get("/api/v1/bookings").json()
    assert anon["code"] == "NOT_AUTHENTICATED"
