"""Download links a report gives the customer: every photo, or every video, of the inspection in
one ZIP. The link is the report's own token (the one behind the verify QR); it works for 30 days
after the booking's first PDF (a PDF made later leaves the links out). The ZIP behind it is built
when someone opens it and cached 7 days (apps.media.zips).

What goes in: the files the counted inspection names in its photo or video fields that show for
this car (a field its show-if rules hide stays out), never the start or end forms, another
expert's files or Ops' uploads no answer uses."""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.core.errors import fail
from apps.media import zips
from apps.media.models import MediaAsset

from .models import Report

# link name -> (media kind, zip kind)
LINKS = {"photos": ("photo", "photo"), "videos": ("video", "video")}
LINK_DAYS = 30           # from the booking's first PDF (R-09)


def expired(booking) -> bool:
    first = Report.objects.filter(booking=booking).values_list("first_generated_at",
                                                               flat=True).first()
    return first is not None and timezone.now() > first + timedelta(days=LINK_DAYS)


def url(token: str, link: str) -> str:
    return f"{settings.VERIFY_BASE_URL}/{token}/{link}"


def allowed_fields(src, link: str) -> set[str]:
    kind = LINKS[link][0]
    return {k for k, f in src.fields.get("inspection", {}).items()
            if f.type == kind and src.shown(f"inspection.{k}")}


def named(src, link: str) -> list[str]:
    """Ids of the files the counted inspection names in the fields this link covers."""
    return sorted({i for k in allowed_fields(src, link) for i in src.media(f"inspection.{k}")})


def _assets(src, link: str):
    return MediaAsset.objects.filter(booking=src.booking, status="verified",
                                     replaced_at__isnull=True, kind=LINKS[link][0],
                                     pk__in=named(src, link))


def count(src, link: str) -> int:
    return _assets(src, link).count()


def values(src) -> dict[str, str]:
    """sys values: photos_url, videos_url ("" once the links expired), photo_count, video_count."""
    out, gone = {}, expired(src.booking)
    for link in LINKS:
        out[f"{link}_url"] = "" if gone else url(src.token, link)
        out[f"{link[:-1]}_count"] = str(count(src, link))
    return out


class ReportMedia(APIView):
    """Public, behind a link in the PDF: starts (or reuses) the ZIP and says where to wait for
    it. The report token is the credential, as for the verify page."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public"

    def get(self, request, token, link):
        from . import context

        r = Report.objects.filter(token=token, status="ready").select_related("booking").first()
        insp = r.booking.counted_inspection() if r else None
        if r is None or insp is None or link not in LINKS:
            raise fail("NOT_FOUND", "No such report.", 404)
        if expired(r.booking):
            raise fail("LINK_EXPIRED", f"The {link} link lasted {LINK_DAYS} days after the "
                       "report was first made.", 410)
        src = context.Source(r.booking, insp, revision=r.revision, token=token)
        ids = named(src, link)
        n = _assets(src, link).count()
        if not n:
            purged = MediaAsset.objects.filter(booking=r.booking, kind=LINKS[link][0],
                                               status="purged", pk__in=ids).exists()
            if purged:                     # Admin's retention setting deleted them
                raise fail("MEDIA_REMOVED", f"These {link} are no longer kept on our server.",
                           410)
            raise fail("NO_MEDIA", f"This report has no {link}.", 404)
        z = zips.request_zip(r.booking, LINKS[link][1], only=ids)
        return Response({"booking_id": r.booking.booking_id, "link": link, "count": n,
                         "zip": f"zips/{zips.token_for(z.id)}"})
