import pytest
import responses

from apps.bookings.tests.conftest import booking, create, env  # noqa: F401
from apps.bookings.tests.test_submissions import ienv  # noqa: F401
from apps.forms.models import Form
from apps.integrations import webhooks
from apps.media.tests.conftest import s3  # noqa: F401  (autouse: in-memory S3)

HOOK = "https://hooks.example.com/vayu"


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    monkeypatch.setattr(webhooks, "resolve", lambda host: ["93.184.216.34"])


@pytest.fixture
def http():
    with responses.RequestsMock(assert_all_requests_are_fired=False) as r:
        r.add(responses.POST, HOOK, status=200, body="ok")
        yield r


def make(env, form, **over):
    body = {"form": form, "name": "ERP", "url": HOOK, "event": "booking.created", **over}
    r = env.admin.post("/api/v1/integrations", body, format="json")
    assert r.status_code == 201, r.json()
    return r.json()


def booking_form_id() -> int:
    return Form.objects.get(type="booking").id
