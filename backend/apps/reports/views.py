from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import perm, scope_for
from apps.bookings.models import Booking
from apps.bookings.services import err
from apps.bookings.submissions import own_filter
from apps.forms.models import Form, MasterListItem
from apps.media import storage

from . import context, service, tasks
from .models import PdfTemplate, PdfTemplateVersion, Report


def _template_body(t: PdfTemplate) -> dict:
    return {"id": t.id, "form": t.form_id, "form_key": t.form.key,
            "versions": [{"id": v.id, "number": v.number, "status": v.status}
                         for v in t.versions.order_by("number")]}


def _version_body(v: PdfTemplateVersion) -> dict:
    return {"id": v.id, "template": v.template_id, "number": v.number, "status": v.status,
            "definition": v.definition, "row_version": v.row_version}


class Templates(APIView):
    permission_classes = [perm("pdf_templates.view", "pdf_templates.edit")]

    def get(self, request):
        return Response([_template_body(t) for t in
                         PdfTemplate.objects.select_related("form").order_by("form__key")])

    def post(self, request):
        form = get_object_or_404(Form, pk=request.data.get("form"))
        return Response(_template_body(service.create_template(request.user, form)),
                        status=status.HTTP_201_CREATED)


class VersionDetail(APIView):
    permission_classes = [perm("pdf_templates.view", "pdf_templates.edit")]

    def get(self, request, pk):
        return Response(_version_body(get_object_or_404(PdfTemplateVersion, pk=pk)))

    def patch(self, request, pk):
        if "row_version" not in request.data or "definition" not in request.data:
            raise ValidationError({"detail": "definition and row_version are required."})
        v = service.save_definition(request.user, get_object_or_404(PdfTemplateVersion, pk=pk),
                                    request.data["definition"], request.data["row_version"])
        return Response(_version_body(v))


class Drafts(APIView):
    permission_classes = [perm("pdf_templates.edit")]

    def post(self, request, pk):
        v = service.create_draft(request.user, get_object_or_404(PdfTemplate, pk=pk))
        return Response(_version_body(v), status=status.HTTP_201_CREATED)


class Publish(APIView):
    permission_classes = [perm("pdf_templates.edit")]

    def post(self, request, pk):
        if "row_version" not in request.data:
            raise ValidationError({"row_version": "This field is required."})
        v = service.publish(request.user, get_object_or_404(PdfTemplateVersion, pk=pk),
                            request.data["row_version"])
        return Response(_version_body(v))


class Preview(APIView):
    """Render this template version with a real booking's data (nothing is stored)."""

    permission_classes = [perm("pdf_templates.edit")]

    def post(self, request, pk):
        tv = get_object_or_404(PdfTemplateVersion.objects.select_related("template__form"), pk=pk)
        if scope_for(request.user, "reports.view", request) is None:
            raise err("FORBIDDEN", "Previews use real data, so they need reports.view.", 403)
        booking = _report_booking(request, request.data.get("booking"))
        insp = context.latest_inspection(booking)
        if insp is None or insp.form_version.form_id != tv.template.form_id:
            raise err("INVALID_BOOKING", "Pick a submitted booking inspected with this form.")
        pdf, name = tasks.build_pdf(booking, insp, tv, "preview", 0)
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{name}"'
        return response


def _report_booking(request, pk) -> Booking:
    qs = Booking.objects.all()
    if scope_for(request.user, "reports.view", request) == "own":
        qs = qs.filter(own_filter(request.user)).distinct()
    return get_object_or_404(qs, pk=pk)


class BookingReport(APIView):
    permission_classes = [perm("reports.view")]

    def get(self, request, pk):
        b = _report_booking(request, pk)
        r = Report.objects.filter(booking=b).first()
        if r is None:
            raise err("NO_REPORT", "No report has been generated yet.", 404)
        return Response({"revision": r.revision, "status": r.status, "stale": r.stale,
                         "generated_at": r.generated_at, "filename": r.filename, "error": r.error,
                         "url": storage.presign_get(r.key, r.filename) if r.status == "ready"
                         else None})


class Regenerate(APIView):
    permission_classes = [perm("reports.regenerate")]

    def post(self, request, pk):
        b = _report_booking(request, pk)
        if b.stage != "completed":
            raise err("NOT_COMPLETED", "Only a completed booking has a report.", 409)
        tasks.render_report.delay(str(b.id))
        r = Report.objects.filter(booking=b).first()
        return Response({"status": r.status if r else "pending",
                         "revision": r.revision if r else 0}, status=status.HTTP_202_ACCEPTED)


class Problems(APIView):
    permission_classes = [perm("reports.view")]

    def get(self, request):
        qs = Report.objects.filter(status="failed") | Report.objects.filter(stale=True)
        if scope_for(request.user, "reports.view", request) == "own":
            qs = qs.filter(booking__in=Booking.objects.filter(own_filter(request.user)))
        return Response([{"booking": str(r.booking_id), "booking_id": r.booking.booking_id,
                          "status": r.status, "stale": r.stale, "error": r.error}
                         for r in qs.select_related("booking").distinct()])


class Verify(APIView):
    """Public page behind the QR code: proves a report is genuine. Summary only, no customer
    data."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, request, token):
        r = Report.objects.filter(token=token, status="ready").select_related("booking").first()
        if r is None:
            raise err("NOT_FOUND", "No such report.", 404)
        b = r.booking
        insp = context.latest_inspection(b)
        car = MasterListItem.objects.filter(list__key="car_make_model", key=b.car_make_model) \
            .values_list("label", flat=True).first() or b.car_make_model
        kind = MasterListItem.objects.filter(list__key="inspection_type", key=b.inspection_type) \
            .values_list("label", flat=True).first() or b.inspection_type
        word = ((insp.scores or {}).get("overall") or {}).get("word") if insp else None
        return Response({"valid": True, "booking_id": b.booking_id, "car": car, "type": kind,
                         "date": b.inspection_date, "overall_rating": word,
                         "revision": r.revision, "generated_at": r.generated_at,
                         "current": not r.stale})


__all__ = ["generics"]
