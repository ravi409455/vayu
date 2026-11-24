import base64

from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import perm, scope_for
from apps.bookings.models import Booking
from apps.bookings.services import err
from apps.bookings.submissions import own_filter
from apps.forms.access import may_see_submissions
from apps.forms.models import Form, MasterListItem
from apps.media import storage

from . import context, service, shared, tasks, transfer
from .definition import validate_definition
from .models import PdfTemplate, PdfTemplateVersion, Report, SharedItem


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

    def delete(self, request, pk):
        service.discard_draft(request.user, get_object_or_404(PdfTemplateVersion, pk=pk))
        return Response(status=status.HTTP_204_NO_CONTENT)

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
        if "definition" in request.data:          # the designer: unsaved edits, with positions
            try:
                d = validate_definition(request.data["definition"])
            except ValueError as e:
                raise err("INVALID_TEMPLATE", str(e)) from e
            pdf, name, layout = tasks.preview(booking, insp, d)
            return Response({"filename": name, "pages": layout,
                             "pdf": base64.b64encode(pdf).decode()})
        pdf, name = tasks.build_pdf(booking, insp, tv, "preview", 0, edge=480)
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{name}"'
        return response


class Checks(APIView):
    """What the designer warns about: fields or sections the form lacks (publishing is blocked)
    and fields of the form the layout never shows."""

    permission_classes = [perm("pdf_templates.view", "pdf_templates.edit")]

    def post(self, request, pk):
        tv = get_object_or_404(PdfTemplateVersion.objects.select_related("template__form"), pk=pk)
        d = request.data.get("definition", tv.definition)
        try:
            d = validate_definition(d)
        except ValueError as e:
            raise err("INVALID_TEMPLATE", str(e)) from e
        return Response({"issues": service.definition_issues(tv.template, d),
                         "unused": service.unused_fields(tv.template, d)})


def _report_booking(request, pk) -> Booking:
    qs = Booking.objects.all()
    if scope_for(request.user, "reports.view", request) == "own":
        qs = qs.filter(own_filter(request.user)).distinct()
    b = get_object_or_404(qs, pk=pk)
    # the report is the submission: judged by every form it could come from (the form of any
    # inspection actually on this booking, and any form of its type, switched off or not)
    forms = Form.objects.filter(type="custom").filter(
        Q(inspection_type=b.inspection_type)
        | Q(pk__in=b.inspections.values("form_version__form_id")))
    if any(not may_see_submissions(request.user, f) for f in forms):
        raise err("NOT_FOUND", "Booking not found.", 404)
    return b


class BookingReport(APIView):
    permission_classes = [perm("reports.view")]

    def get(self, request, pk):
        b = _report_booking(request, pk)
        r = Report.objects.filter(booking=b).first()
        if r is None:
            raise err("NO_REPORT", "No report has been generated yet.", 404)
        return Response({"revision": r.revision, "status": r.status, "stale": r.stale,
                         "generated_at": r.generated_at, "filename": r.filename, "error": r.error,
                         "verify_url": f"{settings.VERIFY_BASE_URL}/{r.token}",
                         "url": storage.presign_get(r.key, r.filename) if r.status == "ready"
                         else None,
                         # same file, shown in the page instead of downloaded
                         "preview_url": storage.presign_get(r.key) if r.status == "ready"
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
        killed = timezone.now() - tasks.STUCK_AFTER       # a render that never finished
        qs = (Report.objects.filter(status="failed") | Report.objects.filter(stale=True)
              | Report.objects.filter(render_started_at__lt=killed))
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
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public"

    def get(self, request, token):
        r = Report.objects.filter(token=token, status="ready").select_related("booking").first()
        if r is None:
            raise err("NOT_FOUND", "No such report.", 404)
        b = r.booking
        insp = context.latest_inspection(b)
        car = MasterListItem.objects.filter(list__key="car_make_model", key=b.car_make_model) \
            .values_list("label", flat=True).first() or b.car_make_model
        kind = Form.objects.filter(type="custom", inspection_type=b.inspection_type) \
            .values_list("name", flat=True).first() or b.inspection_type
        word = ((insp.scores or {}).get("overall") or {}).get("word") if insp else None
        return Response({"valid": True, "booking_id": b.booking_id, "car": car, "type": kind,
                         "date": b.inspection_date, "overall_rating": word,
                         "revision": r.revision, "generated_at": r.generated_at,
                         "current": not r.stale})


# ---------------------------------------------------------------- sharing (docs/plan-reports.md §9)

def _picture(a) -> dict:
    return {"id": str(a.id), "name": a.name, "size": a.size, "content_type": a.content_type,
            "url": f"/api/v1/form-assets/{a.id}"}


def _in_use(asset_id: str) -> bool:
    import json

    from .models import SharedRevision

    return any(asset_id in json.dumps(d) for d in [
        *PdfTemplateVersion.objects.values_list("definition", flat=True),
        *SharedRevision.objects.values_list("content", flat=True)])


class Pictures(generics.GenericAPIView):
    """The picture library: logos, watermarks and backgrounds, uploaded once, used anywhere."""

    permission_classes = [perm("pdf_templates.view", "pdf_templates.edit")]

    def get(self, request):
        from apps.forms.models import FormAsset

        return Response([_picture(a) for a in
                         FormAsset.objects.exclude(name="").order_by("name", "created_at")])

    def post(self, request):
        from apps.forms import assets

        file, name = request.FILES.get("file"), str(request.data.get("name", "")).strip()
        if file is None or not name:
            raise ValidationError({"detail": "Choose a picture and give it a name."})
        a = assets.create_asset(request.user, file.read(assets.MAX_BYTES + 1), name[:100])
        return Response(_picture(a), status=status.HTTP_201_CREATED)


class Picture(APIView):
    permission_classes = [perm("pdf_templates.edit")]

    def _get(self, pk):
        from apps.forms.models import FormAsset

        return get_object_or_404(FormAsset.objects.exclude(name=""), pk=pk)

    def patch(self, request, pk):
        a = self._get(pk)
        name = str(request.data.get("name", "")).strip()
        if not name:
            raise ValidationError({"name": "Give the picture a name."})
        a.name = name[:100]
        a.save(update_fields=["name"])
        return Response(_picture(a))

    def delete(self, request, pk):
        a = self._get(pk)
        if _in_use(str(a.id)):
            raise err("PICTURE_IN_USE", "A template or shared theme still uses this picture.", 409)
        a.name = ""                       # out of the library; the stored file stays harmless
        a.save(update_fields=["name"])
        return Response(status=status.HTTP_204_NO_CONTENT)


def _shared_body(item: SharedItem, content: bool = False) -> dict:
    body = {"id": item.id, "kind": item.kind, "key": item.key, "name": item.name,
            "revision": item.revision, "used_by": shared.usage(item)}
    if content:
        body["content"] = item.revisions.get(revision=item.revision).content
    return body


class SharedItems(APIView):
    """Shared themes and parts. POST saves a new version and moves every template using it."""

    permission_classes = [perm("pdf_templates.view", "pdf_templates.edit")]

    def get(self, request):
        qs = SharedItem.objects.order_by("kind", "name")
        if kind := request.query_params.get("kind"):
            qs = qs.filter(kind=kind)
        return Response([_shared_body(i) for i in qs])

    def post(self, request):
        d = request.data
        item, updated = shared.save(request.user, d.get("kind"), d.get("key"), d.get("name"),
                                    d.get("content"))
        return Response({**_shared_body(item, content=True), "updated": updated},
                        status=status.HTTP_201_CREATED)


class SharedItemDetail(APIView):
    permission_classes = [perm("pdf_templates.view", "pdf_templates.edit")]

    def get(self, request, pk):
        item = get_object_or_404(SharedItem, pk=pk)
        body = _shared_body(item, content=True)
        if rev := request.query_params.get("revision"):
            r = item.revisions.filter(revision=int(rev) if rev.isdigit() else 0).first()
            if r is None:
                raise err("NOT_FOUND", "No such version.", 404)
            body["content"], body["revision"] = r.content, r.revision
        return Response(body)


class CopyTemplate(APIView):
    """A new template for another form, starting from this template's newest layout."""

    permission_classes = [perm("pdf_templates.edit")]

    def post(self, request, pk):
        t = get_object_or_404(PdfTemplate, pk=pk)
        form = get_object_or_404(Form, pk=request.data.get("form"))
        last = t.versions.order_by("-number").first()
        assert last is not None
        return Response(_template_body(transfer.copy_template(request.user, last, form)),
                        status=status.HTTP_201_CREATED)


class ExportTemplate(APIView):
    permission_classes = [perm("pdf_templates.view", "pdf_templates.edit")]

    def get(self, request, pk):
        v = get_object_or_404(PdfTemplateVersion.objects.select_related("template__form"), pk=pk)
        response = Response(transfer.export_file(v))
        response["Content-Disposition"] = (f'attachment; filename="{v.template.form.key}'
                                           f'-report-v{v.number}.json"')
        return response


class ImportTemplate(APIView):
    """The file replaces the draft; what the form lacks comes back as issues to fix."""

    permission_classes = [perm("pdf_templates.edit")]

    def post(self, request, pk):
        out = transfer.import_file(request.user, get_object_or_404(PdfTemplate, pk=pk),
                                   request.data)
        return Response({**_version_body(out["version"]), "issues": out["issues"],
                         "notes": out["notes"]})


__all__ = ["generics"]
