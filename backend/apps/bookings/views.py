import re
import uuid
from datetime import date

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.accounts.permissions import perm, scope_for

from . import services, submissions
from .models import Booking, Inspection
from .serializers import BookingSerializer, InspectionSerializer

ACTION_PERMISSIONS = {
    "list": "bookings.view", "retrieve": "bookings.view", "create": "bookings.create",
    "partial_update": "bookings.edit", "change_type": "bookings.edit",
    "assign": "bookings.assign", "reschedule": "bookings.reschedule", "cancel": "bookings.cancel",
    "force_release": "bookings.force_release", "destroy": "bookings.delete",
    "start": "submissions.fill", "submit": "submissions.fill", "inspections": "submissions.view",
}


class BookingViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                     mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    serializer_class = BookingSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    declared_permissions = tuple(sorted(set(ACTION_PERMISSIONS.values())))

    def get_permissions(self):
        key = ACTION_PERMISSIONS.get(self.action)
        return [perm(key)()] if key else [perm("bookings.view")()]

    def get_queryset(self):
        qs = Booking.objects.select_related("last_edited_by", "released_by").prefetch_related(
            "reschedules__by")
        key = ACTION_PERMISSIONS.get(self.action, "bookings.view")
        scoped = ("bookings.view", "bookings.edit", "submissions.fill", "submissions.view")
        if key in scoped and scope_for(self.request.user, key, self.request) == "own":
            qs = qs.filter(submissions.own_filter(self.request.user)).distinct()
        return self._filtered(qs) if self.action == "list" else qs

    def _filtered(self, qs):
        p = self.request.query_params
        for param, column in (("stage", "stage"), ("type", "inspection_type"), ("city", "city"),
                              ("expert", "assigned_expert_id")):
            if p.get(param):
                if param == "expert" and not p[param].isdigit():
                    raise ValidationError({param: "Use a user id."})
                qs = qs.filter(**{column: p[param]})
        for param, lookup in (("date_from", "inspection_date__gte"),
                              ("date_to", "inspection_date__lte")):
            if p.get(param):
                try:
                    qs = qs.filter(**{lookup: date.fromisoformat(p[param])})
                except ValueError as e:
                    raise ValidationError({param: "Use YYYY-MM-DD."}) from e
        term = (p.get("search") or "").strip()
        if term:
            stages = submissions.searchable_stages(getattr(self.request.user, "role", ""))
            q = Q(pk__in=[])
            for column in ("booking_id", "customer_name", "car_make_model", "chassis_no"):
                q |= Q(**{f"{column}__icontains": term}, stage__in=stages.get(column, []))
            digits = re.sub(r"\D", "", term)
            if len(digits) >= 4:
                q |= Q(customer_phone__contains=digits, stage__in=stages.get("customer_phone", []))
            qs = qs.filter(q)
        return qs

    def create(self, request, *args, **kwargs):
        b = services.create(request.user, request.data.get("answers") or {})
        return Response(self.get_serializer(b).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        if "row_version" not in request.data:
            raise ValidationError({"row_version": "This field is required."})
        b = services.edit(request.user, self.get_object(), request.data.get("answers") or {},
                          request.data["row_version"])
        return Response(self.get_serializer(b).data)

    def destroy(self, request, *args, **kwargs):
        services.delete(request.user, self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _out(self, b):
        return Response(self.get_serializer(Booking.objects.get(pk=b.pk)).data)

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        return self._out(services.assign(request.user, self.get_object(),
                                         request.data.get("expert")))

    @action(detail=True, methods=["post"])
    def reschedule(self, request, pk=None):
        d = request.data
        return self._out(services.reschedule(request.user, self.get_object(), d.get("date"),
                                             d.get("time"), d.get("reason")))

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._out(services.cancel(request.user, self.get_object(),
                                         request.data.get("reason")))

    @action(detail=True, methods=["post"], url_path="force-release")
    def force_release(self, request, pk=None):
        return self._out(services.force_release(request.user, self.get_object()))

    @action(detail=True, methods=["post"], url_path="change-type")
    def change_type(self, request, pk=None):
        return self._out(services.change_type(request.user, self.get_object(),
                                              request.data.get("inspection_type")))


    def _uuid(self, name):
        try:
            return uuid.UUID(str(self.request.data.get(name)))
        except ValueError as e:
            raise ValidationError({name: "A UUID is required."}) from e

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        raw = request.headers.get("X-App-Version", "")
        app_version = int(raw) if raw.isdigit() else None
        started = request.data.get("client_started_at")
        b, insp = submissions.start(
            request.user, self.get_object(), self._uuid("client_uuid"),
            parse_datetime(started) if isinstance(started, str) else None,
            request.data.get("inspection_type"), app_version)
        ctx = self.get_serializer_context()
        return Response({
            "booking": BookingSerializer(Booking.objects.get(pk=b.pk), context=ctx).data,
            "inspection": InspectionSerializer(insp, context=ctx).data,
            "form": submissions.form_for_role(insp.form_version, request.user.role, "in_progress"),
            # the check-in / wrap-up form (payment, review...) the expert also fills in
            "ops_form": (submissions.form_for_role(ov, request.user.role, "in_progress")
                         if (ov := submissions.ops_version()) is not None else None),
            "server_time": timezone.now().isoformat()})

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        version = request.data.get("form_version")
        b, insp = submissions.submit(
            request.user, self.get_object(), self._uuid("client_submission_uuid"),
            request.data.get("answers") or {}, version if isinstance(version, int) else None)
        ctx = self.get_serializer_context()
        return Response({
            "booking": BookingSerializer(Booking.objects.get(pk=b.pk), context=ctx).data,
            "inspection": InspectionSerializer(insp, context=ctx).data,
            "server_time": timezone.now().isoformat()})

    @action(detail=True, methods=["get"])
    def inspections(self, request, pk=None):
        qs = self.get_object().inspections.all()
        if scope_for(request.user, "submissions.view", request) == "own":
            qs = qs.filter(expert_id=request.user.pk)
        return Response(InspectionSerializer(qs, many=True,
                                             context=self.get_serializer_context()).data)


class InspectionDetail(generics.RetrieveUpdateAPIView):
    serializer_class = InspectionSerializer
    http_method_names = ["get", "patch", "head", "options"]
    declared_permissions = ("submissions.view", "submissions.edit")

    def get_permissions(self):
        return [perm("submissions.view", "submissions.edit")()]

    def get_queryset(self):
        qs = Inspection.objects.select_related("booking", "form_version", "last_edited_by")
        key = "submissions.view" if self.request.method == "GET" else "submissions.edit"
        if scope_for(self.request.user, key, self.request) == "own":
            qs = qs.filter(expert_id=self.request.user.pk)
        return qs

    def partial_update(self, request, *args, **kwargs):
        if "row_version" not in request.data:
            raise ValidationError({"row_version": "This field is required."})
        insp = submissions.edit_inspection(request.user, self.get_object(),
                                           request.data.get("answers") or {},
                                           request.data["row_version"])
        return Response(InspectionSerializer(insp, context=self.get_serializer_context()).data)


class InspectionOverrides(generics.GenericAPIView):
    permission_classes = [perm("ratings.override")]
    serializer_class = InspectionSerializer
    http_method_names = ["patch", "head", "options"]

    def patch(self, request, pk):
        if "row_version" not in request.data:
            raise ValidationError({"row_version": "This field is required."})
        insp = get_object_or_404(Inspection, pk=pk)
        body = {k: v for k, v in request.data.items() if k != "row_version"}
        insp = submissions.set_overrides(request.user, insp, body, request.data["row_version"])
        return Response(InspectionSerializer(insp, context=self.get_serializer_context()).data)
