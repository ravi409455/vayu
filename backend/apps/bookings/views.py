import re
import uuid
from datetime import date

from django.db.models import DateTimeField, OuterRef, Q, Subquery, Value
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.accounts.permissions import perm, scope_for
from apps.forms.access import hidden_inspection_forms

from . import services, submissions, sync, timing
from .models import Booking, Inspection
from .serializers import BookingSerializer, InspectionSerializer

ACTION_PERMISSIONS = {
    "list": "bookings.view", "retrieve": "bookings.view", "create": "bookings.create",
    "partial_update": "bookings.edit", "change_type": "bookings.edit",
    "assign": "bookings.assign", "reschedule": "bookings.reschedule", "cancel": "bookings.cancel",
    "force_release": "bookings.force_release", "destroy": "bookings.delete",
    "resolve_conflict": "bookings.edit", "activity": "bookings.view",
    "start": "submissions.fill", "forms": "submissions.fill", "submit": "submissions.fill",
    "inspections": "submissions.view", "timing_review": "bookings.review_timing",
    "answer_fields": "submissions.view", "clear_alert": "bookings.edit",
    "count": "bookings.view",
}


def _pinned_form(version, role):
    return submissions.form_for_role(version, role, "in_progress") if version else None


class BookingViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                     mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    serializer_class = BookingSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    declared_permissions = tuple(sorted(set(ACTION_PERMISSIONS.values())))

    def get_permissions(self):
        key = ACTION_PERMISSIONS.get(self.action)
        return [perm(key)()] if key else [perm("bookings.view")()]

    def get_queryset(self):
        qs = Booking.objects.select_related(
            "last_edited_by", "released_by", "late_reviewed_by", "quick_reviewed_by",
        ).prefetch_related("reschedules__by")
        key = ACTION_PERMISSIONS.get(self.action, "bookings.view")
        scoped = ("bookings.view", "bookings.edit", "submissions.fill", "submissions.view")
        if key in scoped and scope_for(self.request.user, key, self.request) == "own":
            # start / submit: also a job moved away while its expert worked offline
            rule = (submissions.deliver_filter if self.action in ("start", "submit")
                    else submissions.own_filter)
            qs = qs.filter(rule(self.request.user)).distinct()
        if self.action not in ("list", "count"):
            return qs
        # only submissions this user may see, the same rule as the `inspections` action
        done = Inspection.objects.filter(booking=OuterRef("pk"), status="submitted").exclude(
            form_version__form_id__in=hidden_inspection_forms(self.request.user))
        scope = scope_for(self.request.user, "submissions.view", self.request)
        if scope is None:                           # may not see submissions at all: no time
            return self._filtered(qs).annotate(
                finished_at=Value(None, output_field=DateTimeField()))
        if scope == "own":
            done = done.filter(expert_id=self.request.user.pk)
        return self._filtered(qs).annotate(finished_at=Subquery(
            done.order_by("-submitted_at").values("submitted_at")[:1]))

    def _filtered(self, qs):
        p = self.request.query_params
        for param, column in (("stage", "stage"), ("type", "inspection_type"), ("city", "city"),
                              ("expert", "assigned_expert_id")):
            if p.get(param):
                if param == "expert":                 # one id or several: expert=3,7
                    ids = p[param].split(",")
                    if not all(i.isdigit() for i in ids):
                        raise ValidationError({param: "Use user ids, separated by commas."})
                    qs = qs.filter(assigned_expert_id__in=ids)
                    continue
                qs = qs.filter(**{column: p[param]})
        problem = p.get("problem")                    # the Ops problem queue
        if problem == "conflict":
            qs = qs.exclude(conflict="")
        elif problem == "type_change":
            qs = qs.filter(alerts__contains=[{"code": "TYPE_CHANGE_REJECTED"}])
        elif problem:
            raise ValidationError({"problem": "Use conflict or type_change."})
        if p.get("timing") or p.get("reviewed"):          # started late / finished too quickly
            if scope_for(self.request.user, "bookings.review_timing", self.request) is None:
                raise PermissionDenied("You may not see timing flags.")
            cfg = timing.config()
            flag = p.get("timing")
            if flag not in ("late", "quick"):
                raise ValidationError({"timing": "Use late or quick."})
            qs = qs.filter(timing.late_q(cfg) if flag == "late" else timing.quick_q(cfg))
            if p.get("reviewed") in ("0", "1"):
                qs = qs.filter(**{f"{flag}_reviewed_at__isnull": p["reviewed"] == "0"})
            elif p.get("reviewed"):
                raise ValidationError({"reviewed": "Use 0 or 1."})
        if p.get("answer"):                           # any choice / yes-no answer (answers_filter)
            from . import answers_filter
            scope = scope_for(self.request.user, "submissions.view", self.request)
            if scope is None:
                raise PermissionDenied("You may not see inspection answers.")
            qs = answers_filter.apply(qs, self.request.user, p["answer"], p.get("value", ""),
                                      own=scope == "own")
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
        if p.get("order") == "schedule":                 # Today / Upcoming: soonest first
            qs = qs.order_by("inspection_date", "answers__inspection_time", "booking_id")
        elif p.get("order"):
            raise ValidationError({"order": "Use schedule."})
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

    @action(detail=False, methods=["get"])
    def count(self, request):
        """How many bookings the list would give for the same filters, without loading them (the
        Bookings filter's counts, F-085)."""
        return Response({"count": self.get_queryset().count()})

    @action(detail=False, methods=["get"], url_path="answer-fields")
    def answer_fields(self, request):
        """Fields Bookings can be filtered by (choice and yes/no answers this person may see)."""
        from . import answers_filter
        return Response(answers_filter.fields_for(request.user, request.query_params.get("type")))

    @action(detail=True, methods=["post"], url_path="force-release")
    def force_release(self, request, pk=None):
        return self._out(services.force_release(request.user, self.get_object()))

    @action(detail=True, methods=["post"], url_path="resolve-conflict")
    def resolve_conflict(self, request, pk=None):
        # keeping the other expert's inspection hands them the booking: that is an assignment too
        if scope_for(request.user, "bookings.assign", request) is None:
            raise PermissionDenied("Resolving a conflict also needs the assign permission.")
        return self._out(submissions.resolve_conflict(request.user, self.get_object(),
                                                      request.data.get("inspection")))

    @action(detail=True, methods=["post"], url_path="timing-review")
    def timing_review(self, request, pk=None):
        """Mark one flag ({"flag": "late"} or "quick") as looked at: it leaves "Needs you"."""
        return self._out(services.review_timing(request.user, self.get_object(),
                                                request.data.get("flag")))

    @action(detail=True, methods=["post"], url_path="clear-alert")
    def clear_alert(self, request, pk=None):
        """Ops looked at an alert ({"code": "TYPE_CHANGE_REJECTED"}): it leaves "Needs you" and
        the timeline says who cleared it (F-221)."""
        return self._out(services.clear_alert(request.user, self.get_object(),
                                              request.data.get("code")))

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
        """Start a lead with its check-in. ``form_version``, ``start_version``, ``end_version``:
        the versions the phone pinned when the expert started, kept if each was the latest
        published one at ``client_started_at`` (give or take 10 minutes); an older one is refused
        (409 ``FORM_VERSION_OLD``, Ops alerted). Left out: the latest published versions."""
        raw = request.headers.get("X-App-Version", "")
        app_version = int(raw) if raw.isdigit() else None
        started = request.data.get("client_started_at")
        b, insp = submissions.start(
            request.user, self.get_object(), self._uuid("client_uuid"),
            parse_datetime(started) if isinstance(started, str) else None,
            request.data.get("inspection_type"), app_version, request.data.get("start_answers"),
            {part: request.data.get(key) for part, key in (
                ("inspection", "form_version"), ("start", "start_version"),
                ("end", "end_version"))})
        ctx = self.get_serializer_context()
        return Response({
            "booking": BookingSerializer(Booking.objects.get(pk=b.pk), context=ctx).data,
            "inspection": InspectionSerializer(insp, context=ctx).data,
            **self._forms(insp.pinned(), request.user.role),
            "server_time": timezone.now().isoformat()})

    def _forms(self, pinned, role):
        return {"form": submissions.form_for_role(pinned["inspection"], role, "in_progress"),
                # the start form (check-in) and end form (wrap-up) an inspection goes through;
                # null when the form does not use it. Pinned at start: they never change after.
                "start_form": _pinned_form(pinned["start"], role),
                "end_form": _pinned_form(pinned["end"], role)}

    @action(detail=True, methods=["get"])
    def forms(self, request, pk=None):
        """The forms the expert fills in, before the job is started (it only becomes in progress
        once the check-in is done)."""
        b = self.get_object()
        return Response(self._forms(submissions.current_versions(b), request.user.role))

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
    def activity(self, request, pk=None):
        """The booking's timeline, newest first (field keys hidden from this person left out)."""
        from . import activity

        return Response(activity.for_user(self.get_object(), request.user))

    @action(detail=True, methods=["get"])
    def inspections(self, request, pk=None):
        qs = self.get_object().inspections.exclude(
            form_version__form_id__in=hidden_inspection_forms(request.user))
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
        qs = Inspection.objects.select_related("booking", "form_version", "last_edited_by").exclude(
            form_version__form_id__in=hidden_inspection_forms(self.request.user))
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
        insp = get_object_or_404(Inspection.objects.exclude(
            form_version__form_id__in=hidden_inspection_forms(request.user)), pk=pk)
        body = {k: v for k, v in request.data.items() if k != "row_version"}
        insp = submissions.set_overrides(request.user, insp, body, request.data["row_version"])
        return Response(InspectionSerializer(insp, context=self.get_serializer_context()).data)


class SyncJobs(generics.GenericAPIView):
    """The expert's jobs and everything needed to inspect them offline (see apps/bookings/sync.py).
    ``have`` lists form version ids the phone already holds; ``drafts`` the ones its open drafts
    are pinned to (sent when missing, even if no listed job uses them); ``since`` is the last
    sync's ``server_time`` (returns what Ops changed after it)."""

    permission_classes = [perm("submissions.fill")]

    def get(self, request):
        since_raw = request.query_params.get("since")
        since = parse_datetime(since_raw) if since_raw else None
        have, drafts = ([p for p in request.query_params.get(name, "").split(",") if p]
                        for name in ("have", "drafts"))
        if (since_raw and since is None) or not all(p.isdigit() for p in have + drafts):
            raise services.err("INVALID_QUERY",
                               "have and drafts must be version ids, since a date-time.")
        return Response(sync.payload(request.user, {int(p) for p in have}, since,
                                     self.get_serializer_context(), {int(p) for p in drafts}))
