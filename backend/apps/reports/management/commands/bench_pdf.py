"""Benchmark: how long does one report with N photos take? (REQUIREMENTS: 150 photos <= 2 min.)

Run on the machine that will render (staging), against the real bucket. It creates a temporary
booking, inspection and N verified photos, renders the PDF the way the worker does, prints the
time and size, and removes everything again (database rows and bucket files)."""
import io
import random
import time
import uuid

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from PIL import Image

from apps.accounts.models import User
from apps.bookings.models import Booking, Inspection
from apps.forms.models import Form, FormVersion
from apps.media import storage
from apps.media.models import MediaAsset
from apps.reports import render, tasks
from apps.reports.models import PdfTemplateVersion

LIMIT_SECONDS = 120


class _Rollback(Exception):
    pass


def photo(seed: int) -> bytes:
    """A 2048 px picture with texture (a flat colour would compress to nothing)."""
    rnd = random.Random(seed)
    tint = Image.new("RGB", (2048, 1536), tuple(rnd.randrange(256) for _ in range(3)))
    img = Image.blend(Image.effect_noise((2048, 1536), 60).convert("RGB"), tint, 0.4)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


class Command(BaseCommand):
    help = "Time the PDF render of a report with many photos (rolls everything back afterwards)."

    def add_arguments(self, parser):
        parser.add_argument("--photos", type=int, default=150)
        parser.add_argument("--form", default="pdi", help="inspection form key with a photo field")
        parser.add_argument("--field", default="door_photo")

    def handle(self, *args, photos, form, field, **options):
        f = Form.objects.filter(key=form, type="custom").first()
        published = FormVersion.objects.filter(form=f, status="published")
        version = published.order_by("-number").first() if f else None
        if f is None or version is None:
            raise CommandError(f"No published inspection form '{form}'.")
        expert = User.objects.filter(role="expert").first() or User.objects.first()
        if expert is None:
            raise CommandError("There are no users to attribute the benchmark data to.")
        keys: list[str] = []
        try:
            with transaction.atomic():
                b = Booking.objects.create(
                    booking_id=f"BENCH-{uuid.uuid4().hex[:6]}", stage="completed",
                    inspection_type=f.inspection_type, customer_name="Benchmark",
                    answers={"booking_id": "BENCH"}, assigned_expert=expert)
                ids = []
                for n in range(photos):
                    sample = photo(n)       # all different: a PDF keeps a repeated picture once
                    a = MediaAsset(client_uuid=uuid.uuid4(), booking=b, uploaded_by=expert,
                                   field_key=field, kind="photo", content_type="image/jpeg",
                                   size=len(sample), sha256="0" * 64, status="verified")
                    a.key = f"bench/{b.id}/{a.id}"
                    storage.put(a.key, sample, "image/jpeg")
                    keys.append(a.key)
                    a.save()
                    ids.append(str(a.id))
                insp = Inspection.objects.create(
                    booking=b, expert=expert, form_version=version, status="submitted",
                    answers={"inspection": {field: ids}, "start": {}, "end": {}})
                tv = PdfTemplateVersion(definition={"schema": 2, "pages": [{
                    "title": "Photos", "parts": [{"type": "photos", "title": "Photos",
                                                  "per_row": 3, "source": {
                                                      "kind": "fields",
                                                      "fields": [f"inspection.{field}"]}}]}]})
                keys += [f"print/{i}-{e}.jpg" for i in ids                    # shrunk copies
                         for e in (render.PRINT_EDGE, render.SMALL_EDGE)]
                start = time.monotonic()
                pdf, _name = tasks.build_pdf(b, insp, tv, "bench", 1)
                took = time.monotonic() - start
                verdict = "PASS" if took <= LIMIT_SECONDS else "TOO SLOW"
                self.stdout.write(f"{photos} photos -> {len(pdf) / 1e6:.1f} MB PDF in {took:.1f} s "
                                  f"({verdict}: target {LIMIT_SECONDS} s)")
                raise _Rollback
        except _Rollback:
            pass
        finally:
            for k in keys:
                storage.delete(k)
