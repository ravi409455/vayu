"""A file field marked "Hide from customer" (owner, 2026-11-27: payment and other internal photos)
never leaves the app: not in the report, its download links, partner integrations or any ZIP.
The newest published version of the form decides, so older bookings follow it too."""
from unittest import mock

import pytest

from apps.bookings.models import Booking
from apps.forms.models import Field
from apps.media import zips
from apps.media.models import MediaAsset
from apps.media.services import customer_hidden
from apps.media.tests.conftest import initiate_body, jpeg
from apps.media.tests.test_upload import job, menv, submit_with  # noqa: F401

pytestmark = pytest.mark.django_db


def done(env, b):
    """The expert submitted two photos and a video, every file verified."""
    ids = {}
    for i, (k, kind, ct) in enumerate((("photo_a", "photo", "image/jpeg"), ("clip", "video", "video/mp4"))):
        r = env.expert.post("/api/v1/media/initiate", initiate_body(
            b["id"], jpeg(color=(i, 2, 2)), field_key=k, kind=kind, content_type=ct), format="json")
        assert r.status_code == 201, r.json()
        ids[k] = r.json()["id"]
    assert submit_with(env, b, photo_a=[ids["photo_a"]], clip=[ids["clip"]]).status_code == 200
    MediaAsset.objects.filter(pk__in=ids.values()).update(status="verified")
    return ids


def hide(key, on=True):
    """Set it on the published version, the way a publish of a new version would."""
    for f in Field.objects.filter(key=key, version__status="published"):
        f.config = {**f.config, "hide_from_customer": on}
        Field.objects.filter(pk=f.pk).update(config=f.config)


def test_the_builder_accepts_the_setting_on_photo_video_and_document_fields_only(menv):
    env = menv
    sec = Field.objects.filter(key="photo_a").values_list("section_id", flat=True).first()
    bad = env.admin.post(f"/api/v1/sections/{sec}/fields", {"key": "x", "label": "x", "type": "photo",
                         "config": {"hide_from_customer": "yes"}}, format="json")
    assert bad.status_code == 400
    text = env.admin.post(f"/api/v1/sections/{sec}/fields", {"key": "y", "label": "y", "type": "short_text",
                          "config": {"hide_from_customer": True}}, format="json")
    assert text.status_code == 400


def test_hidden_files_stay_out_of_every_zip_and_are_tagged_for_ops(job, settings):
    env, b = job
    ids = done(env, b)
    booking = Booking.objects.get(pk=b["id"])
    assert customer_hidden(booking) == set()
    with mock.patch("apps.media.zips.build_zip.delay"):
        before = zips.request_zip(booking, "image")
        hide("photo_a")
        assert customer_hidden(booking) == {"photo_a"}
        after = zips.request_zip(booking, "image")         # Ops, report links, partners alike
    assert after.id != before.id and "photo_a" in after.excluded and "photo_a" not in before.excluded
    rows = {r["id"]: r for r in env.ops.get(f"/api/v1/bookings/{b['id']}/media").json()}
    assert rows[ids["photo_a"]]["hidden_from_customer"] is True
    assert rows[ids["clip"]]["hidden_from_customer"] is False


def test_the_newest_published_version_decides_for_older_bookings(job, settings):
    from apps.bookings.tests.test_submissions import publish_form

    env, b = job
    done(env, b)
    booking = Booking.objects.get(pk=b["id"])
    pinned = booking.counted_inspection().form_version

    def publish_with(on):
        assert env.admin.post(f"/api/v1/forms/{pinned.form_id}/drafts").status_code in (200, 201)
        form = env.admin.get(f"/api/v1/forms/{pinned.form_id}").json()
        f = Field.objects.get(version_id=form["draft_version"]["id"], key="photo_a")
        r = env.admin.patch(f"/api/v1/fields/{f.id}", {"config": {**f.config, "hide_from_customer": on}},
                            format="json")
        assert r.status_code == 200, r.json()
        publish_form(env.admin, pinned.form_id)

    publish_with(True)
    assert Booking.objects.get(pk=b["id"]).counted_inspection().form_version == pinned   # still pinned
    assert customer_hidden(booking) == {"photo_a"}         # the old booking follows the new setting
    publish_with(False)
    assert customer_hidden(booking) == set()               # and turning it off again too


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


def test_the_report_leaves_hidden_photos_out_and_its_download_link_too(job, settings):
    from apps.reports import context, media_links

    env, b = job
    ids = done(env, b)
    booking = Booking.objects.get(pk=b["id"])
    src = context.Source(booking, booking.counted_inspection())
    part = {"source": {"kind": "fields", "fields": ["inspection.photo_a"]}}
    assert [p["media"] for p in context.photo_items(src, part)] == [ids["photo_a"]]
    assert media_links.named(src, "photos") == [ids["photo_a"]]
    hide("photo_a")
    src = context.Source(booking, booking.counted_inspection())
    assert context.photo_items(src, part) == []            # placed by name: skipped, no warning
    assert media_links.named(src, "photos") == []
