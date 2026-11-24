from django.http import HttpResponseRedirect
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import perm, perm_any, scope_for
from apps.bookings.models import Booking
from apps.bookings.services import err
from apps.bookings.submissions import own_filter

from . import services, storage, zips
from .models import MediaAsset


def _asset(request, pk, *, write=True) -> MediaAsset:
    asset = MediaAsset.objects.select_related("booking").filter(pk=pk).first()
    if asset is None:
        raise err("NOT_FOUND", "Media not found.", 404)
    (services.writable_booking if write else services.readable_booking)(request, asset.booking_id)
    return asset


class Initiate(APIView):
    permission_classes = [perm_any("submissions.fill", "media.manage")]

    def post(self, request):
        body, created = services.initiate(request, request.data)
        return Response(body, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class Detail(APIView):
    declared_permissions = ("submissions.fill", "media.manage")

    permission_classes = [perm_any("submissions.fill", "media.manage")]

    def get(self, request, pk):
        return Response(services.progress(_asset(request, pk)))

    def delete(self, request, pk):
        services.remove(request, _asset(request, pk))
        return Response(status=status.HTTP_204_NO_CONTENT)


class BookingMedia(APIView):
    permission_classes = [perm_any("submissions.fill", "media.manage")]

    def get(self, request, pk):
        return Response(services.booking_media(request, pk))


class Complete(APIView):
    permission_classes = [perm_any("submissions.fill", "media.manage")]

    def post(self, request, pk):
        parts = request.data.get("parts")
        if not isinstance(parts, list) or not all(
                isinstance(p, dict) and isinstance(p.get("part_number"), int)
                and isinstance(p.get("etag"), str) for p in parts):
            raise ValidationError({"parts": "A list of {part_number, etag} is required."})
        asset = services.complete(_asset(request, pk), parts)
        return Response(services.progress(asset))


class Attach(APIView):
    """Ops put a file they uploaded into the submitted inspection, or swap it for an old one."""

    permission_classes = [perm("media.manage")]

    def post(self, request, pk):
        services.attach(request, _asset(request, pk), request.data.get("replaces"))
        return Response(status=status.HTTP_204_NO_CONTENT)


class Url(APIView):
    permission_classes = [perm("submissions.view")]

    def get(self, request, pk):
        asset = _asset(request, pk, write=False)
        if asset.field_key in services.hidden_fields(request.user, asset.booking) or (
                asset.replaced_at is not None and request.user.role != "admin"):  # history: Admin
            raise err("NOT_FOUND", "Media not found.", 404)      # same answer as a missing file
        if asset.status != "verified":
            raise err("NOT_READY", "This file is not verified yet.", 409)
        return Response({"url": storage.presign_get(asset.key),
                         "preview_url": storage.presign_get(asset.preview_key)
                         if asset.preview_key else None,
                         "content_type": asset.content_type})


class StuckUploads(APIView):
    permission_classes = [perm("bookings.view")]

    def get(self, request):
        qs = services.stuck_uploads().select_related("booking", "uploaded_by")
        if scope_for(request.user, "bookings.view", request) == "own":
            qs = qs.filter(booking__in=Booking.objects.filter(own_filter(request.user)))
        return Response([{"id": str(a.id), "booking": str(a.booking_id),
                          "booking_id": a.booking.booking_id, "field_key": a.field_key,
                          "status": a.status, "expert": a.uploaded_by.username,
                          "created_at": a.created_at} for a in qs])


class RequestZip(APIView):
    permission_classes = [perm("media.download")]

    def post(self, request, pk):
        kind = request.data.get("kind")
        if kind not in zips.KIND_TYPES:
            raise ValidationError({"kind": "Use image or video."})
        booking = services.readable_booking(request, pk)
        z = zips.request_zip(booking, kind, sorted(services.hidden_fields(request.user, booking)))
        return Response({"url": f"/api/v1/zips/{zips.token_for(z.id)}", "status": z.status},
                        status=status.HTTP_202_ACCEPTED)


class ZipDownload(APIView):
    """Opened from a link in Slack: no login, the signed token is the credential."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public"

    def get(self, request, token):
        z = zips.zip_from_token(token)
        if z is None or not zips.fresh(z):
            raise err("LINK_EXPIRED", "This download link is invalid or has expired.", 404)
        if z.status == "ready":
            url = storage.presign_get(z.key, zips.download_name(z))
            if request.query_params.get("format") == "json":    # the "Preparing..." web page
                return Response({"status": "ready", "progress": 100, "url": url})
            return HttpResponseRedirect(url)
        if z.status == "failed":
            raise err("NO_MEDIA", "There is nothing to download.", 404)
        return Response({"status": z.status, "progress": z.progress},
                        status=status.HTTP_202_ACCEPTED)
