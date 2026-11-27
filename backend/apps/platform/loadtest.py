"""Load tests (docs/plan-load-test.md): the test form and the clean-up, on a TEST server only.

`loadtest_prepare` makes the test data (and, with --test-form, the form below); `loadtest_cleanup`
deletes the files it left in the file bucket. Nothing here wipes anything: on a throwaway server
the bucket is staging's, so files are only ever deleted by the keys of load-test bookings
(booking IDs starting with LT-)."""
import copy

from django.conf import settings

from apps.accounts.models import User
from apps.forms.models import Field, Form
from apps.platform.setup import testdata

PREFIX = "LT-"                           # every load-test booking (loadtest_prepare's)
TEST_FORM = "loadtest"                   # a copy of PDI with an extra last page
EXTRA_PHOTO_FIELDS = 4                   # +100 photos (25 each) and +10 videos


class Refused(Exception):
    pass


def check_test_server() -> None:
    """A test (or local) server by its settings AND by what its database says."""
    kind = testdata.stored_kind()
    if settings.SERVER_KIND not in testdata.WIPEABLE or kind not in (None, *testdata.WIPEABLE):
        raise Refused(f"This server is '{kind or settings.SERVER_KIND}': load-test data only goes "
                      "on a test or local server. Nothing was changed.")


def make_test_form(admin: User) -> str:
    """The test's inspection form (owner, 2026-11-27): a copy of PDI, its PDF template included,
    with a last page "Load test extra media" (4 photo fields of up to 25 and one video field of
    up to 10), so an inspection can really send 100 (or 150) photos and 15 videos; the PDF prints
    that page's photos too. Only on this throwaway server's database."""
    from apps.forms import services as forms
    from apps.forms.models import FormVersion, Page, Section, VersionStatus
    from apps.reports import service as pdf
    from apps.reports.models import PdfTemplateVersion

    if Form.objects.filter(key=TEST_FORM).exists():
        return "exists"
    forms.duplicate_form(admin, Form.objects.get(key="pdi"), TEST_FORM, "Load test (PDI copy)")
    form = Form.objects.get(key=TEST_FORM)
    Form.objects.filter(pk=form.pk).update(inspection_type=TEST_FORM)
    draft = FormVersion.objects.get(form=form, status=VersionStatus.DRAFT)
    last = Page.objects.filter(version=draft).order_by("-order").first()
    page = Page.objects.create(version=draft, title="Load test extra media",
                               order=(last.order + 1) if last else 0)
    section = Section.objects.create(version=draft, page=page, title="Load test extra media")
    for n in range(1, EXTRA_PHOTO_FIELDS + 1):
        Field.objects.create(version=draft, section=section, key=f"lt_photos_{n}",
                             label=f"Extra photos {n}", type="photo", order=n,
                             config={"max_count": 25})
    Field.objects.create(version=draft, section=section, key="lt_videos", label="Extra videos",
                         type="video", order=EXTRA_PHOTO_FIELDS + 1, config={"max_count": 10})
    draft.refresh_from_db()
    forms.publish_version(admin, draft.id, draft.row_version)
    section.refresh_from_db()
    t = PdfTemplateVersion.objects.filter(template__form=form, status="draft").first()
    if t is not None:
        d = copy.deepcopy(t.definition)
        page_tpl = {k: v for k, v in (d["pages"][-1] if d.get("pages") else {}).items()
                    if k not in ("parts", "id")}
        d.setdefault("pages", []).append({**page_tpl, "parts": [{
            "type": "photos", "title": "Load test extra media",
            "source": {"kind": "section", "section": f"inspection.{section.key}"}}]})
        t.definition = d
        t.save()
        t.refresh_from_db()
        pdf.publish(admin, t, t.row_version)
    return "made"


def cleanup() -> dict[str, int]:
    """Delete from the bucket every file the load-test bookings point at (their files, previews,
    copies and PDFs), then check nothing is left in those bookings' folders. Only keys of LT-
    bookings are touched. Fast on a 3-month history (about a million file rows): rows are read as
    plain values, print copies are counted only for original uploads (a history copy points at
    the original's keys and has no print copies of its own), and deletes go 1,000 per request."""
    from apps.bookings.models import Booking
    from apps.media import storage
    from apps.media.models import MediaAsset
    from apps.reports.models import Report
    from apps.reports.render import print_keys

    check_test_server()
    ids = set(Booking.objects.filter(booking_id__startswith=PREFIX).values_list("id", flat=True))
    keys: set[str] = set()
    real: set = set()                                             # bookings with their own uploads
    rows = MediaAsset.objects.filter(booking_id__in=ids).values_list(
        "id", "booking_id", "key", "preview_key", "jpeg_key").iterator(chunk_size=5000)
    for aid, bid, key, preview, jpeg in rows:
        keys.update(k for k in (key, preview, jpeg) if k)
        if key and key.startswith(f"bookings/{bid}/"):            # an original upload
            keys.update(print_keys(aid))
            real.add(bid)
    keys.update(Report.objects.filter(booking_id__in=ids).exclude(key="")
                .values_list("key", flat=True))
    client = storage.client()
    for bid in real:                     # every PDF version of a run's booking (Regenerate)
        for page in client.get_paginator("list_objects_v2").paginate(
                Bucket=settings.S3_BUCKET, Prefix=f"reports/{bid}/"):
            keys.update(o["Key"] for o in page.get("Contents", []))
    ordered = sorted(keys)
    for i in range(0, len(ordered), 1000):
        client.delete_objects(Bucket=settings.S3_BUCKET, Delete={
            "Objects": [{"Key": k} for k in ordered[i:i + 1000]], "Quiet": True})
    folders = {"/".join(k.split("/")[:2]) + "/" for k in keys if k.startswith("bookings/")}
    left = sum(client.list_objects_v2(Bucket=settings.S3_BUCKET, Prefix=f).get("KeyCount", 0)
               for f in folders)
    return {"bookings": len(ids), "files_deleted": len(keys), "left_in_their_folders": left}
