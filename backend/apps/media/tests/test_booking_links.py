"""A booking's file links in one answer (bookings/<id>/media-links): the same rule as one file's
link (media/<id>/url), checked file by file, and a fixed number of database queries."""
import uuid
from typing import Any

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.forms.models import Field
from apps.media.models import MediaAsset
from apps.media.tests.conftest import jpeg, upload
from apps.media.tests.test_upload import job, menv, submit_with  # noqa: F401

pytestmark = pytest.mark.django_db


def links(client, b):
    r = client.get(f"/api/v1/bookings/{b['id']}/media-links")
    assert r.status_code == 200, r.content
    return r.json()


def same_as_one_by_one(client, b):
    """Every file of the booking: in the links exactly when its own link call answers 200."""
    got = links(client, b)["links"]
    for a in MediaAsset.objects.filter(booking_id=b["id"]):
        one = client.get(f"/api/v1/media/{a.id}/url")
        assert (str(a.id) in got) == (one.status_code == 200), (a.status, one.status_code)
        if one.status_code == 200:
            assert got[str(a.id)]["content_type"] == one.json()["content_type"]
            assert bool(got[str(a.id)]["preview_url"]) == bool(one.json()["preview_url"])
    return got


def test_links_for_every_verified_file_with_previews(job, settings):
    env, b = job
    ids = [upload(env.expert, b["id"], jpeg(color=(i, 9, 9)), settings).json()["id"] for i in range(2)]
    assert submit_with(env, b, photo_a=ids).status_code == 200
    body = links(env.ops, b)
    assert set(body["links"]) == set(ids)
    assert body["expires_in"] == settings.MEDIA_URL_TTL
    for link in body["links"].values():
        assert link["url"].startswith("https://") and link["preview_url"].startswith("https://")
        assert link["content_type"] == "image/jpeg"
    same_as_one_by_one(env.ops, b)


@pytest.mark.parametrize("why", ["purged", "not_verified", "replaced"])
def test_files_without_a_link_are_left_out(job, settings, why):
    env, b = job
    keep, drop = (upload(env.expert, b["id"], jpeg(color=(c, 9, 9)), settings).json()["id"] for c in (1, 2))
    assert submit_with(env, b, photo_a=[keep, drop]).status_code == 200
    changes: dict[str, dict[str, Any]] = {
        "purged": {"status": "purged"}, "not_verified": {"status": "uploaded"},
        "replaced": {"replaced_at": timezone.now()}}
    MediaAsset.objects.filter(pk=drop).update(**changes[why])
    assert set(same_as_one_by_one(env.ops, b)) == {keep}


def test_hidden_fields_are_left_out_except_for_admin(job, settings):
    env, b = job
    a = upload(env.expert, b["id"], jpeg(), settings).json()["id"]
    assert submit_with(env, b, photo_a=[a]).status_code == 200
    Field.objects.filter(key="photo_a").update(access={"ops": {"completed": "hidden"}})
    assert same_as_one_by_one(env.ops, b) == {}
    assert set(same_as_one_by_one(env.admin, b)) == {a}


def test_no_links_to_a_booking_one_may_not_read(job, settings):
    env, b = job
    upload(env.expert, b["id"], jpeg(), settings)
    other = env.make_user("expert", username="e12")
    c = APIClient()
    c.force_authenticate(user=other)
    assert c.get(f"/api/v1/bookings/{b['id']}/media-links").status_code == 404
    assert APIClient().get(f"/api/v1/bookings/{b['id']}/media-links").status_code in (401, 403)


def test_queries_do_not_grow_with_the_number_of_files(job, settings, django_assert_max_num_queries):
    env, b = job
    ids = [upload(env.expert, b["id"], jpeg(color=(i, 9, 9)), settings).json()["id"] for i in range(2)]
    assert submit_with(env, b, photo_a=ids).status_code == 200
    from django.db import connection
    from django.test.utils import CaptureQueriesContext
    with CaptureQueriesContext(connection) as two:
        links(env.ops, b)
    for i in range(6):                                   # 6 more files on the booking
        MediaAsset.objects.create(booking_id=b["id"], field_key="photo_a", kind="photo", client_uuid=uuid.uuid4(),
                                  status="verified", key=f"k{i}", size=1, sha256="0" * 64,
                                  content_type="image/jpeg", uploaded_by=env.expert_user)
    with django_assert_max_num_queries(len(two)):
        assert len(links(env.ops, b)["links"]) == 8
