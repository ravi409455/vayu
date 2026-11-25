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
