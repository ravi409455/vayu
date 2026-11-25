"""The REST API for other systems (API key auth). A key sees and writes only the forms and fields
in its scope; DELETE needs the key to have been given it explicitly."""
import uuid
from typing import cast

from django.db import transaction
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import audit
from apps.bookings import services, submissions
from apps.bookings.models import Booking, Inspection
from apps.core.errors import CodedError
from apps.forms.models import Form, FormType

from .apikeys import ApiKeyAuthentication
from .models import ApiKey

BULK_LIMIT = 100


class HasApiKey(BasePermission):
    def has_permission(self, request, view):
        return isinstance(request.auth, ApiKey)


def scope_of(request, form: Form | None) -> list[str] | None:
    """The field keys this key may use on a form (["*"] = all); None = form not in scope."""
    if form is None:
        return None
    return request.auth.scope.get("forms", {}).get(form.key)


def permitted(allowed: list[str] | None, key: str) -> bool:
    return allowed is not None and (allowed == ["*"] or key in allowed)


def need_form(request, form: Form | None) -> list[str]:
    allowed = scope_of(request, form)
    if allowed is None:
        raise CodedError("OUT_OF_SCOPE", "This key may not use that form.", 403)
    return allowed


def need_keys(allowed: list[str], keys) -> None:
    bad = sorted(k for k in keys if not permitted(allowed, k))
    if bad:
        raise CodedError("OUT_OF_SCOPE", "This key may not write these fields.", 403, keys=bad)


def only(answers: dict, allowed: list[str]) -> dict:
    return {k: v for k, v in (answers or {}).items() if permitted(allowed, k)}


def booking_form() -> Form | None:
    return Form.objects.filter(type=FormType.BOOKING, is_active=True).first()


def inspection_form(b: Booking) -> Form | None:
    return Form.objects.filter(type=FormType.CUSTOM, is_active=True,
                               inspection_type=b.inspection_type).first()


def find(ref: str) -> Booking:
    """A booking by internal ID (primary) or by Booking ID."""
    try:
        b = Booking.objects.filter(pk=uuid.UUID(ref)).first()
    except ValueError:
        b = Booking.objects.filter(booking_id__iexact=ref).first()
    if b is None:
        raise CodedError("NOT_FOUND", "Booking not found.", 404)
    return b


def booking_body(request, b: Booking, allowed: list[str] | None = None) -> dict:
    """[allowed]: the key's booking fields when the caller already looked them up (a list)."""
    allowed = need_form(request, booking_form()) if allowed is None else allowed
    return {"id": str(b.id), "booking_id": b.booking_id, "stage": b.stage,
            "inspection_type": b.inspection_type, "assigned_expert": b.assigned_expert_id,
            "row_version": b.row_version, "created_at": b.created_at,
            "data": only(b.answers, allowed)}


class ExtView(APIView):
    authentication_classes = [ApiKeyAuthentication]
    permission_classes = [HasApiKey]


class Bookings(ExtView):
    def get(self, request):
        allowed = need_form(request, booking_form())
        qs = Booking.objects.all()
        p = request.query_params
        for param, column in (("stage", "stage"), ("type", "inspection_type"),
                              ("city", "city")):
            if p.get(param):
                qs = qs.filter(**{column: p[param]})
        if p.get("search"):
            qs = qs.filter(booking_id__icontains=p["search"].strip())
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([booking_body(request, b, allowed)
                                                 for b in page or []])

    def post(self, request):
        allowed = need_form(request, booking_form())
        answers = request.data.get("answers")
        if not isinstance(answers, dict):
            raise ValidationError({"answers": "An object of field keys and values is required."})
        need_keys(allowed, answers)
        if answers.get("assigned_expert"):          # choosing the expert is the assign action
            need_action(request, "assign")
        b = services.create(request.user, answers)
        audit.record(request.user, "api.booking.create", "booking", b.id,
                     f"Created booking {b.booking_id} via API key {request.auth.prefix}")
        return Response(booking_body(request, b), status=201)


def update_booking(request, ref: str, answers, row_version=None) -> Booking:
    allowed = need_form(request, booking_form())
    if not isinstance(answers, dict):
        raise ValidationError({"answers": "An object of field keys and values is required."})
    need_keys(allowed, answers)
    if {"inspection_date", "inspection_time"} & set(answers):   # moving it is a reschedule
        need_action(request, "reschedule")
    b = find(ref)
    # an API write is last-write-wins unless the caller sends the row_version it read
    b = services.edit(request.user, b, answers, b.row_version if row_version is None
                      else row_version)
    return b


class BookingDetail(ExtView):
    def get(self, request, ref):
        return Response(booking_body(request, find(ref)))

    def patch(self, request, ref):
        b = update_booking(request, ref, request.data.get("answers"),
                           request.data.get("row_version"))
        return Response(booking_body(request, b))

    def delete(self, request, ref):
        need_form(request, booking_form())
        if not request.auth.allow_delete:
            raise CodedError("DELETE_NOT_ALLOWED",
                             "This key may not delete. Ask an Admin to allow it.", 403)
        b = find(ref)
        audit.record(request.user, "api.booking.delete", "booking", b.id,
                     f"Deleted booking {b.booking_id} via API key {request.auth.prefix}")
        services.delete(request.user, b)
        return Response(status=204)


def need_action(request, action: str) -> None:
    if action not in (request.auth.allowed_actions or []):
        raise CodedError("ACTION_NOT_ALLOWED", f"This key may not {action.replace('_', ' ')}. "
                         "Ask an Admin to allow it.", 403)


class BookingAction(ExtView):
    """POST ext/bookings/<ref>/<action>: assign (or reassign) {"expert"}, cancel {"reason"},
    reschedule {"date", "time", "reason"}, change-type {"inspection_type"}. Each one is a flag on
    the key, off by default (F-228); audited; the same rules and webhooks as on the web."""

    ACTIONS = {
        "assign": lambda u, b, d: services.assign(u, b, d.get("expert")),
        "cancel": lambda u, b, d: services.cancel(u, b, d.get("reason")),
        "reschedule": lambda u, b, d: services.reschedule(u, b, d.get("date"), d.get("time"),
                                                          d.get("reason")),
        "change_type": lambda u, b, d: services.change_type(u, b, d.get("inspection_type")),
    }

    # the booking fields each action writes: the key's field scope must cover them too
    WRITES = {"assign": ["assigned_expert"], "cancel": [],
              "reschedule": ["inspection_date", "inspection_time"],
              "change_type": ["inspection_type"]}

    def post(self, request, ref, action):
        name = action.replace("-", "_")
        if name not in self.ACTIONS:
            raise CodedError("UNKNOWN_ACTION", "Use assign, cancel, reschedule or change-type.",
                             404)
        need_keys(need_form(request, booking_form()), self.WRITES[name])
        need_action(request, name)
        b = self.ACTIONS[name](request.user, find(ref), request.data)
        audit.record(request.user, f"api.booking.{name}", "booking", b.id,
                     f"{name.replace('_', ' ').capitalize()} {b.booking_id} via API key "
                     f"{request.auth.prefix}")
        return Response(booking_body(request, Booking.objects.get(pk=b.pk)))


def _error(e: APIException) -> dict:
    if isinstance(e, CodedError):
        return dict(cast(dict, e.detail))
    return {"code": e.default_code, "detail": e.detail}


class BulkBookings(ExtView):
    """PATCH many bookings. Each item succeeds or fails on its own; the reply lists both."""

    def post(self, request):
        items = request.data.get("items")
        if not isinstance(items, list) or not items or len(items) > BULK_LIMIT:
            raise ValidationError({"items": f"Send 1 to {BULK_LIMIT} items."})
        results = []
        for item in items:
            ref = item.get("ref") if isinstance(item, dict) else None
            try:
                if not isinstance(ref, str):
                    raise ValidationError({"ref": "A booking id or Booking ID is required."})
                with transaction.atomic():
                    b = update_booking(request, ref, item.get("answers"), item.get("row_version"))
                results.append({"ref": ref, "ok": True, "booking": booking_body(request, b)})
            except APIException as e:
                results.append({"ref": ref, "ok": False, "error": _error(e)})
        return Response({"results": results,
                         "failed": sum(1 for r in results if not r["ok"])})


def latest_inspection(b: Booking) -> Inspection:
    insp = b.inspections.order_by("-created_at").first()
    if insp is None:
        raise CodedError("NO_INSPECTION", "This booking has no inspection yet.", 404)
    return insp


class BookingInspection(ExtView):
    def get(self, request, ref):
        b = find(ref)
        allowed = need_form(request, inspection_form(b))
        insp = latest_inspection(b)
        return Response({"id": str(insp.id), "status": insp.status,
                         "row_version": insp.row_version,
                         "data": only(insp.answers.get("inspection") or {}, allowed)})

    def patch(self, request, ref):
        b = find(ref)
        allowed = need_form(request, inspection_form(b))
        answers = request.data.get("answers")
        if not isinstance(answers, dict):
            raise ValidationError({"answers": "An object of field keys and values is required."})
        need_keys(allowed, answers)
        # only the inspection that counts: a draft is overwritten by the expert's submit, a
        # superseded one never reaches the report
        insp = b.counted_inspection()
        if insp is None:
            raise CodedError("NOT_SUBMITTED", "This booking has no submitted inspection yet.", 409)
        rv = request.data.get("row_version")
        insp = submissions.edit_inspection(request.user, insp, {"inspection": answers},
                                           insp.row_version if rv is None else rv)
        return Response({"id": str(insp.id), "status": insp.status,
                         "row_version": insp.row_version,
                         "data": only(insp.answers.get("inspection") or {}, allowed)})
