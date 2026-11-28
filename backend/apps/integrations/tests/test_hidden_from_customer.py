"""Integrations are the company's own tools: "Hide from customer" files reach them too (owner,
2026-11-28). The report, its download links and the Ops ZIP still leave them out."""
from types import SimpleNamespace
from unittest import mock

import pytest
from rest_framework.test import APIClient

from apps.bookings.models import Booking
from apps.media import zips
from apps.media.models import MediaZip
from apps.media.tests.test_hide_from_customer import ZIP_URL, done, hide
from apps.media.tests.test_upload import job, menv  # noqa: F401

pytestmark = pytest.mark.django_db


def test_an_integration_gets_links_to_a_hidden_photo(job, settings):
    from apps.integrations.values import Resolver

    env, b = job
    ids = done(env, b)
    hide("photo_a")
    [link] = Resolver(SimpleNamespace(booking_uuid=b["id"], event="inspection.completed",
                                      context={}))._link("photos.photo_a")
    assert ids["photo_a"] in link


def test_an_integration_zip_holds_hidden_files_and_its_link_is_never_rebuilt(job, settings):
    env, b = job
    done(env, b)
    booking = Booking.objects.get(pk=b["id"])
    hide("photo_a")
    with mock.patch("apps.media.zips.build_zip.delay"):
        mine = zips.request_zip(booking, "image", for_customer=False)
        theirs = zips.request_zip(booking, "image")           # Ops, report links
        assert zips.request_zip(booking, "image", for_customer=False).id == mine.id   # cached
        MediaZip.objects.filter(pk=mine.pk).update(status="ready", key="zips/mine.zip")
        r = APIClient().get(f"{ZIP_URL}{zips.token_for(mine.id)}?format=json")
    assert mine.with_hidden and "photo_a" not in mine.excluded
    assert not theirs.with_hidden and "photo_a" in theirs.excluded
    assert r.status_code == 200 and r.json()["status"] == "ready"       # handed out as it is
