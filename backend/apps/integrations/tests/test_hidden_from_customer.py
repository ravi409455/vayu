"""Partners are outside the company: a "Hide from customer" photo gets no links (owner, 2026-11-27)."""
import pytest

from apps.media.tests.test_hide_from_customer import done, hide
from apps.media.tests.test_upload import job, menv  # noqa: F401

pytestmark = pytest.mark.django_db


def test_a_partner_gets_no_links_to_a_hidden_photo(job, settings):
    """Partners (webhooks, external API) only reach files through links the server makes."""
    from types import SimpleNamespace

    from apps.integrations.values import Resolver

    env, b = job
    ids = done(env, b)
    assert ids
    hide("photo_a")
    r = Resolver(SimpleNamespace(booking_uuid=b["id"], event="inspection.completed"))
    assert r._link("photos.photo_a") == []
