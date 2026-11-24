"""Download-all links in a report: every photo or every video of the inspection as one ZIP, behind
the report's own token (docs/plan-reports.md)."""
import io
import uuid
import zipfile
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.media import storage, zips
from apps.media.models import MediaAsset, MediaZip
from apps.reports import context, definition, placeholders, render
from apps.reports.models import Report

from .test_reports import complete_job, one_page, renv, set_template, source  # noqa: F401

pytestmark = pytest.mark.django_db
BUTTONS = [{"type": "button", "link": "photos", "label": "All {{ sys.photo_count }} photos"},
           {"type": "button", "link": "videos", "label": "All videos"}]


@pytest.fixture
def done(renv, settings):
    set_template(renv)
    b = complete_job(renv, settings=settings)               # 2 photo_a + 1 door_photo (dent)
    return renv, b, Report.objects.get(booking_id=b["id"])


def test_sys_values_name_the_links_and_count_what_is_behind_them(done):
    _, b, r = done
    sv = source(b, token=r.token).values()["sys"]
    assert sv["photos_url"] == f"https://verify.carcid.in/{r.token}/photos"
    assert sv["videos_url"] == f"https://verify.carcid.in/{r.token}/videos"
    assert (sv["photo_count"], sv["video_count"]) == ("3", "0")


def test_a_photo_whose_field_is_hidden_for_this_car_stays_out(renv, settings):
    set_template(renv)
    b = complete_job(renv, door="ok", settings=settings)    # door_photo shows only for a dent
    a = MediaAsset.objects.filter(booking_id=b["id"]).first()
    assert a is not None                                     # uploaded, then the answer changed
    a.pk, a.client_uuid, a.field_key = uuid.uuid4(), uuid.uuid4(), "door_photo"
    a.save(force_insert=True)
    r = Report.objects.get(booking_id=b["id"])
    assert source(b, token=r.token).values()["sys"]["photo_count"] == "2"
    body = APIClient().get(f"/api/v1/verify/{r.token}/photos").json()
    assert body["count"] == 2
    assert MediaZip.objects.get().excluded == ["door_photo"]


def test_the_link_builds_one_readable_zip_and_reuses_it(done):
    _, b, r = done
    client = APIClient()
    body = client.get(f"/api/v1/verify/{r.token}/photos").json()
    assert body == {"booking_id": "SA37926", "link": "photos", "count": 3,
                    "zip": body["zip"]}
    ready = client.get(f"/api/v1/{body['zip']}", {"format": "json"}).json()
    assert ready["status"] == "ready" and "SA37926%20photos.zip" in ready["url"]
    z = MediaZip.objects.get()
    assert z.kind == "photo"
    with zipfile.ZipFile(io.BytesIO(storage.read(z.key))) as archive:
        names = archive.namelist()
    # a folder per section, in form order, named by the field's label
    assert names == ["Section 1/door_photo.jpg", "Section 1/photo_a 1.jpg",
                     "Section 1/photo_a 2.jpg"]
    client.get(f"/api/v1/verify/{r.token}/photos")
    assert MediaZip.objects.count() == 1                      # cached for the next customer tap


def test_nothing_to_download_and_bad_links_are_404(done):
    _, _, r = done
    client = APIClient()
    assert client.get(f"/api/v1/verify/{r.token}/videos").json()["code"] == "NO_MEDIA"
    assert client.get(f"/api/v1/verify/{r.token}/selfies").status_code == 404
    assert client.get("/api/v1/verify/nope/photos").status_code == 404
    Report.objects.filter(pk=r.pk).update(status="failed")
    assert client.get(f"/api/v1/verify/{r.token}/photos").status_code == 404


def test_buttons_link_to_the_zip_and_hide_when_there_is_nothing(done):
    _, b, r = done
    d = definition.validate_definition(one_page(*BUTTONS, {"type": "button", "link": "verify",
                                                           "label": "Check", "align": "left"}))
    src = source(b, token=r.token)
    pages = context.build(src, d)
    assert [p["link"] for p in pages[0]["parts"]] == ["photos", "verify"]   # no videos
    html = render.render_html(pages, d, src.values())
    assert f'href="https://verify.carcid.in/{r.token}/photos">All 3 photos</a>' in html
    assert f'href="https://verify.carcid.in/{r.token}"' in html and "text-align:left" in html
    shown = definition.validate_definition(one_page({**BUTTONS[1], "hide_when_empty": False}))
    assert len(context.build(src, shown)[0]["parts"]) == 1


def test_text_links_may_point_only_at_the_report_links():
    ok = '<p><a href="{{ sys.photos_url }}">Photos</a> <a href="https://carcid.in">Us</a></p>'
    d = definition.validate_definition(one_page({"type": "text", "html": ok}))
    assert 'href="{{ sys.photos_url }}"' in d["pages"][0]["parts"][0]["html"]
    for bad in ('<a href="{{ inspection.note }}">x</a>', '<a href="{{ sys.photos_url }}x">x</a>'):
        with pytest.raises(ValueError, match="a link can hold only one of"):
            definition.validate_definition(one_page({"type": "text", "html": bad}))
    band = {"normal": {"header": {"left": [{"text": '<a href="{{ booking.x }}">x</a>'}]}}}
    with pytest.raises(ValueError, match="link"):
        definition.validate_definition({**one_page(), "bands": band})


def test_zip_entry_names_are_safe_unique_and_fall_back_to_the_key():
    a = lambda key, ct="image/jpeg": SimpleNamespace(field_key=key, content_type=ct)  # noqa: E731
    places = {"f1": (0, "Exterior / Body", "Front: bumper?"), "f2": (1, "Exterior / Body",
                                                                    "Front: bumper?")}
    names = zips.entry_names(places, [a("f1"), a("f2"), a("f2"), a("odd", "video/mp4")])
    assert names == ["Exterior - Body/Front- bumper.jpg", "Exterior - Body/Front- bumper 1.jpg",
                     "Exterior - Body/Front- bumper 2.jpg", "odd-1.mp4"]
    same = zips.entry_names({"f1": (0, "S", "X"), "f2": (1, "S", "X")}, [a("f1"), a("f2")])
    assert same == ["S/X.jpg", "S/X (2).jpg"]


# ---------------------------------------------------------------- retention (Admin setting)

def test_retention_setting_accepts_zero_or_30_to_3650_days(renv):
    url = "/api/v1/settings/media"
    assert renv.admin.get(url).json() == {"photo_days": 0, "video_days": 0}
    for bad in (5, 4000, "30", True, None):
        assert renv.admin.put(url, {"photo_days": bad, "video_days": 0},
                              format="json").status_code == 400
    assert renv.admin.put(url, {"photo_days": 90, "video_days": 30},
                          format="json").json() == {"photo_days": 90, "video_days": 30}
    assert renv.ops.put(url, {"photo_days": 0, "video_days": 0}, format="json").status_code == 403


def test_old_photos_of_completed_jobs_are_purged_and_the_link_says_so(done, settings):
    from datetime import timedelta

    from django.utils import timezone

    from apps.bookings.models import Booking
    from apps.core import app_settings
    from apps.media.tasks import purge_expired

    env, b, r = done
    client = APIClient()
    client.get(f"/api/v1/verify/{r.token}/photos")                 # a ZIP exists before
    zip_key = MediaZip.objects.get().key
    assets = list(MediaAsset.objects.filter(booking_id=b["id"]))
    assert purge_expired() == 0                                      # 0 days: kept for ever
    app_settings.put("media", {"photo_days": 30, "video_days": 0})
    assert purge_expired() == 0                                      # not old enough yet
    MediaAsset.objects.filter(booking_id=b["id"]).update(
        created_at=timezone.now() - timedelta(days=31))
    Booking.objects.filter(pk=b["id"]).update(stage="submitted")
    assert purge_expired() == 0                                      # an open job is never touched
    Booking.objects.filter(pk=b["id"]).update(stage="completed")
    assert purge_expired() == len(assets) == 3
    for a in assets:
        assert not storage.exists(a.key)
        assert not a.preview_key or not storage.exists(a.preview_key)
    assert not storage.exists(zip_key) and not MediaZip.objects.exists()
    assert set(MediaAsset.objects.values_list("status", flat=True)) == {"purged"}
    assert purge_expired() == 0                                      # once only
    res = client.get(f"/api/v1/verify/{r.token}/photos")
    assert res.status_code == 410 and res.json()["code"] == "MEDIA_REMOVED"
    assert source(b, token=r.token).values()["sys"]["photo_count"] == "0"   # button hides
    assert storage.exists(Report.objects.get(pk=r.pk).key)           # the PDF itself stays
    from apps.media.services import stuck_uploads
    assert not stuck_uploads(hours=1).exists()                       # not "stuck uploads"


def test_link_check_sees_every_quoting_and_button_labels_are_plain_text(done):
    for bad in ("<a href='{{ inspection.note }}'>x</a>", "<a href={{inspection.note}}>x</a>",
                '<a HREF="{{ booking.x }}">x</a>'):
        with pytest.raises(ValueError, match="link"):
            placeholders.check_links(bad, "t")
    _, b, r = done
    d = definition.validate_definition(one_page(
        {"type": "button", "link": "photos", "label": '<img src="x"> All <b>photos</b>'}))
    src = source(b, token=r.token)
    html = render.render_html(context.build(src, d), d, src.values())
    assert "&lt;img src=&quot;x&quot;&gt; All &lt;b&gt;photos&lt;/b&gt;</a>" in html
