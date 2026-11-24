"""Download links a report gives the customer: every photo, or every video, of the inspection in
one ZIP. The link is the report's own token (the one behind the verify QR), so it works for as
long as the report does; the ZIP behind it is built when someone opens it and cached 7 days
(apps.media.zips).

What goes in: the inspection form's photo or video fields that show for this car (a field its
show-if rules hide stays out), never the start or end forms or Ops' own uploads."""
from django.conf import settings
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.bookings.services import err
from apps.media import zips
from apps.media.models import MediaAsset

from .models import Report

# link name -> (media kind, zip kind)
LINKS = {"photos": ("photo", "photo"), "videos": ("video", "video")}


def url(token: str, link: str) -> str:
    return f"{settings.VERIFY_BASE_URL}/{token}/{link}"


def allowed_fields(src, link: str) -> set[str]:
    kind = LINKS[link][0]
    return {k for k, f in src.fields.get("inspection", {}).items()
            if f.type == kind and src.shown(f"inspection.{k}")}


def _assets(booking, link: str):
    return MediaAsset.objects.filter(booking=booking, status="verified",
                                     replaced_at__isnull=True, kind=LINKS[link][0])


def count(src, link: str) -> int:
    return _assets(src.booking, link).filter(field_key__in=allowed_fields(src, link)).count()


def values(src) -> dict[str, str]:
    """sys values: photos_url, videos_url, photo_count, video_count."""
    out = {}
    for link in LINKS:
        out[f"{link}_url"] = url(src.token, link)
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
        insp = context.latest_inspection(r.booking) if r else None
        if r is None or insp is None or link not in LINKS:
            raise err("NOT_FOUND", "No such report.", 404)
        src = context.Source(r.booking, insp, revision=r.revision, token=token)
        allowed = allowed_fields(src, link)
        assets = _assets(r.booking, link)
        n = assets.filter(field_key__in=allowed).count()
        if not n:
            purged = MediaAsset.objects.filter(booking=r.booking, kind=LINKS[link][0],
                                               status="purged", field_key__in=allowed).exists()
            if purged:                     # Admin's retention setting deleted them
                raise err("MEDIA_REMOVED", f"These {link} are no longer kept on our server.",
                          410)
            raise err("NO_MEDIA", f"This report has no {link}.", 404)
        excluded = set(assets.values_list("field_key", flat=True)) - allowed
        z = zips.request_zip(r.booking, LINKS[link][1], sorted(excluded))
        return Response({"booking_id": r.booking.booking_id, "link": link, "count": n,
                         "zip": f"zips/{zips.token_for(z.id)}"})
