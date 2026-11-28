"""Admin screens' API: webhook integrations, their delivery log, API keys, API docs."""
import json
import uuid
from typing import Any

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import audit
from apps.accounts.permissions import perm
from apps.bookings.models import Booking
from apps.core.errors import fail
from apps.core.pagination import Pages
from apps.forms.models import Field, Form, FormType

from . import apikeys, values, webhooks
from .models import ApiKey, Delivery, Integration
from .serializers import IntegrationSerializer


def body(i: Integration, cache: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"id": str(i.id), "form": i.form_id, "form_key": i.form.key, "name": i.name,
            "event": i.event, "method": i.method, "url": i.url, "query": i.query,
            "headers": i.headers, "body_mode": i.body_mode, "body": i.body,
            "include_data": i.include_data, "include_pdf": i.include_pdf,
            "include_image_zip": i.include_image_zip, "include_video_zip": i.include_video_zip,
            "fields": i.fields, "is_active": i.is_active,
            "broken_refs": values.broken_refs(i, cache=cache),
            "created_at": i.created_at}


def delivery_body(d: Delivery) -> dict[str, Any]:
    return {"id": str(d.id), "integration": str(d.integration_id), "event": d.event,
            "booking": d.booking_uuid, "booking_id": d.booking_ref, "status": d.status,
            "attempts": d.attempts, "response_status": d.response_status, "error": d.error,
            "next_retry_at": d.next_retry_at, "last_attempt_at": d.last_attempt_at,
            "created_at": d.created_at,
            "resent_of": str(d.resent_of_id) if d.resent_of_id else None}


class IntegrationList(APIView):
    permission_classes = [perm("integrations.manage")]

    @extend_schema(operation_id="integrations_list")
    def get(self, request: Request) -> Response:
        qs = Integration.objects.select_related("form")
        if request.query_params.get("form", "").isdigit():
            qs = qs.filter(form_id=request.query_params["form"])
        cache: dict[str, Any] = {}
        return Response([body(i, cache) for i in qs])

    def post(self, request: Request) -> Response:
        s = IntegrationSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        i = Integration(created_by=request.user, **s.validated_data)  # type: ignore[misc]
        i.save()
        audit.record(request.user, "integration.create", "integration", i.id,
                     f"Created integration {i.name} for form {i.form.key}")
        return Response(body(i), status=status.HTTP_201_CREATED)


class IntegrationDetail(APIView):
    permission_classes = [perm("integrations.manage")]

    def _get(self, pk: Any) -> Integration:
        return get_object_or_404(Integration.objects.select_related("form"), pk=pk)

    def get(self, request: Request, pk: Any) -> Response:
        return Response(body(self._get(pk)))

    def patch(self, request: Request, pk: Any) -> Response:
        i = self._get(pk)
        s = IntegrationSerializer(i, data=request.data)
        s.is_valid(raise_exception=True)
        for key, value in s.validated_data.items():
            setattr(i, key, value)
        i.save()
        audit.record(request.user, "integration.update", "integration", i.id,
                     f"Updated integration {i.name}")
        return Response(body(i))

    def delete(self, request: Request, pk: Any) -> Response:
        i = self._get(pk)
        audit.record(request.user, "integration.delete", "integration", i.id,
                     f"Deleted integration {i.name}")
        i.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class EventCatalog(APIView):
    """Every event, or with ?form= the ones that form can use (webhooks.EVENTS_FOR)."""

    permission_classes = [perm("integrations.manage")]

    def get(self, request: Request) -> Response:
        raw = request.query_params.get("form", "").strip()
        if not raw:
            return Response(webhooks.EVENTS)
        form = Form.objects.filter(pk=raw).first() if raw.isdigit() else None
        if form is None or form.type not in webhooks.EVENTS_FOR:
            raise fail("INVALID_FORM", "Choose the booking form, an inspection form or the "
                       "Check-in form.")
        return Response(webhooks.EVENTS_FOR[form.type])


def _booking_for(request: Request, form: Form, submitted: bool = False) -> Booking | None:
    raw = request.data.get("booking")
    if raw:
        try:
            return get_object_or_404(Booking, pk=uuid.UUID(str(raw)))
        except ValueError as e:
            raise ValidationError({"booking": "Not a valid booking id."}) from e
    qs = Booking.objects.all()
    if form.type == FormType.CUSTOM:
        qs = qs.filter(inspection_type=form.inspection_type)
    if form.type == FormType.START:                      # one that has checked in
        qs = qs.filter(inspections__start_version__isnull=False).distinct()
    qs = qs.order_by("-created_at")
    return (qs.filter(inspections__status="submitted").first() if submitted else None) \
        or qs.first()


class TestSend(APIView):
    """The test button: sends a `test.ping` now, with a real booking's data if there is one."""

    permission_classes = [perm("integrations.manage")]

    def post(self, request: Request, pk: Any) -> Response:
        i = get_object_or_404(Integration.objects.select_related("form"), pk=pk)
        booking = _booking_for(request, i.form, submitted=not i.event.startswith("booking."))
        d = Delivery.objects.create(
            integration=i, event="test.ping", booking=booking,
            booking_uuid=str(booking.id) if booking else "",
            booking_ref=booking.booking_id if booking else "", context={"sample": True},
            status="sending")
        d = webhooks.attempt(d)
        if d.status == "retrying":                  # a test is not retried for hours
            d.status, d.next_retry_at = "failed", None
            d.save()
        return Response(delivery_body(d))


class Catalogue(APIView):
    """The picker's list of values for a form and an event (without an event: all of them)."""

    permission_classes = [perm("integrations.manage")]

    def get(self, request: Request) -> Response:
        form = Form.objects.filter(pk=request.query_params.get("form", "").strip() or 0).first()
        event = request.query_params.get("event")
        if form is None or form.type not in webhooks.EVENTS_FOR:
            raise fail("INVALID_FORM", "Choose the booking form, an inspection form or the "
                       "Check-in form.")
        if event is not None and event not in webhooks.EVENTS_FOR[form.type]:
            raise fail("INVALID_EVENT", "Pick one event.", allowed=webhooks.EVENTS_FOR[form.type])
        return Response(values.catalogue(form, event))


class Preview(APIView):
    """The whole request an unsaved integration would send, for a real job or sample values.
    Nothing is sent and no ZIP is built."""

    permission_classes = [perm("integrations.manage")]

    def post(self, request: Request) -> Response:
        data = {**request.data}
        data["name"] = data.get("name") or "preview"          # a preview does not need a name yet
        s = IntegrationSerializer(data=data, check_address=False)
        s.is_valid(raise_exception=True)
        i = Integration(**s.validated_data)
        booking = _booking_for(request, i.form, submitted=not i.event.startswith("booking."))
        d = Delivery(integration=i, event=i.event,
                     booking_uuid=str(booking.id) if booking else "",
                     booking_ref=booking.booking_id if booking else "", context={})
        types = {e["ref"]: e["type"] for e in values.catalogue(i.form, i.event)}
        try:
            req = webhooks.build_request(d, "preview" if booking else "sample", types)
        except values.MissingPathValue as e:
            raise fail("PATH_VALUE_EMPTY", f"{e} is empty for this booking, so the URL cannot be "
                       "built.") from e
        except ValueError as e:                              # the body would be too large
            raise fail("REQUEST_FAILED", f"The request cannot be built: {e}.") from e
        return Response({
            "method": req.method, "url": req.url, "sample": booking is None,
            "headers": [{"name": k, "value": v} for k, v in req.headers.items()],
            "body": json.dumps(json.loads(req.body), indent=2) if req.body else None,
            "booking": str(booking.id) if booking else None,
            "broken_refs": values.broken_refs(i)})


class DeliveryList(APIView):
    permission_classes = [perm("integrations.manage")]

    def get(self, request: Request, pk: Any) -> Response:
        i = get_object_or_404(Integration, pk=pk)
        qs = i.deliveries.all()
        for param in ("status", "event"):
            if request.query_params.get(param):
                qs = qs.filter(**{param: request.query_params[param]})
        paginator = Pages()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([delivery_body(d) for d in page or []])


class Resend(APIView):
    """Manual re-send: a new delivery of the same event, built from today's data."""

    permission_classes = [perm("integrations.manage")]

    def post(self, request: Request, pk: Any) -> Response:
        old = get_object_or_404(Delivery.objects.select_related("integration"), pk=pk)
        d = Delivery.objects.create(
            integration=old.integration, event=old.event, booking=old.booking,
            booking_uuid=old.booking_uuid, booking_ref=old.booking_ref, context=old.context,
            resent_of=old)
        webhooks.send_later(d)
        audit.record(request.user, "integration.resend", "integration", old.integration_id,
                     f"Re-sent {old.event} for {old.booking_ref}")
        return Response(delivery_body(d), status=status.HTTP_202_ACCEPTED)


# ------------------------------------------------------------------ API keys

def _clean_scope(scope: Any) -> dict[str, Any]:
    """{"forms": {form key: [field keys] or ["*"]}} where every name really exists."""
    if not isinstance(scope, dict) or not isinstance(scope.get("forms"), dict) \
            or not scope["forms"] or set(scope) - {"forms"}:
        raise fail("INVALID_SCOPE", 'scope must look like {"forms": {"<form key>": ["<field>"]}}.')
    out: dict[str, Any] = {}
    for key, fields in scope["forms"].items():
        form = Form.objects.filter(key=key, type__in=[FormType.BOOKING, FormType.CUSTOM],
                                   is_active=True).first()
        if form is None:
            raise fail("INVALID_SCOPE", f"'{key}' is not an active booking or inspection form.")
        if fields == ["*"]:
            out[key] = ["*"]
            continue
        if not isinstance(fields, list) or not fields or not all(
                isinstance(f, str) for f in fields):
            raise fail("INVALID_SCOPE", f"List the field keys for '{key}', or [\"*\"].")
        known = set(Field.objects.filter(version__form=form, key__in=fields)
                    .values_list("key", flat=True))
        if set(fields) - known:
            raise fail("INVALID_SCOPE", f"Unknown fields for '{key}': "
                       f"{', '.join(sorted(set(fields) - known))}.")
        out[key] = sorted(set(fields))
    return {"forms": out}


KEY_ACTIONS = ("assign", "cancel", "reschedule", "change_type")


def _clean_actions(raw: Any) -> list[str]:
    if not isinstance(raw, list) or any(a not in KEY_ACTIONS for a in raw):
        raise fail("INVALID_ACTIONS", f"allowed_actions is a list of: {', '.join(KEY_ACTIONS)}.")
    return sorted(set(raw))


def key_body(k: ApiKey, full_key: str | None = None) -> dict[str, Any]:
    out = {"id": str(k.id), "name": k.name, "prefix": k.prefix, "scope": k.scope,
           "allow_delete": k.allow_delete, "allowed_actions": k.allowed_actions,
           "revoked_at": k.revoked_at,
           "last_used_at": k.last_used_at, "created_at": k.created_at}
    if full_key:
        out["key"] = full_key                   # shown once
    return out


class ApiKeyList(APIView):
    permission_classes = [perm("api_keys.manage")]

    @extend_schema(operation_id="api_keys_list")
    def get(self, request: Request) -> Response:
        return Response([key_body(k) for k in ApiKey.objects.all()])

    def post(self, request: Request) -> Response:
        name = request.data.get("name")
        if not isinstance(name, str) or not name.strip() or len(name) > 100:
            raise fail("INVALID_NAME", "Give the key a name (up to 100 characters).")
        allow = request.data.get("allow_delete", False)
        if not isinstance(allow, bool):
            raise fail("INVALID_TOGGLE", "allow_delete must be true or false.")
        scope = _clean_scope(request.data.get("scope"))
        actions = _clean_actions(request.data.get("allowed_actions", []))
        key, prefix, hashed = apikeys.generate()
        k = ApiKey.objects.create(name=name.strip(), prefix=prefix, key_hash=hashed, scope=scope,
                                  allow_delete=allow, allowed_actions=actions,
                                  created_by=request.user)  # type: ignore[misc]
        audit.record(request.user, "api_key.create", "api_key", k.id,
                     f"Created API key {k.name} ({k.prefix}){' with DELETE' if allow else ''}"
                     f"{'; actions ' + ', '.join(actions) if actions else ''}")
        return Response(key_body(k, key), status=status.HTTP_201_CREATED)


class ApiKeyDetail(APIView):
    permission_classes = [perm("api_keys.manage")]

    def get(self, request: Request, pk: Any) -> Response:
        return Response(key_body(get_object_or_404(ApiKey, pk=pk)))

    def patch(self, request: Request, pk: Any) -> Response:
        k = get_object_or_404(ApiKey, pk=pk)
        if k.revoked_at is not None:
            raise fail("KEY_REVOKED", "A revoked key cannot be changed.", 409)
        if "name" in request.data:
            name = request.data["name"]
            if not isinstance(name, str) or not name.strip() or len(name) > 100:
                raise fail("INVALID_NAME", "Give the key a name (up to 100 characters).")
            k.name = name.strip()
        if "scope" in request.data:
            k.scope = _clean_scope(request.data["scope"])
        if "allow_delete" in request.data:
            if not isinstance(request.data["allow_delete"], bool):
                raise fail("INVALID_TOGGLE", "allow_delete must be true or false.")
            k.allow_delete = request.data["allow_delete"]
        if "allowed_actions" in request.data:
            k.allowed_actions = _clean_actions(request.data["allowed_actions"])
        k.save()
        audit.record(request.user, "api_key.update", "api_key", k.id,
                     f"Updated API key {k.name} ({k.prefix}); delete "
                     f"{'allowed' if k.allow_delete else 'off'}; actions "
                     f"{', '.join(k.allowed_actions) or 'none'}")
        return Response(key_body(k))


class ApiKeyRevoke(APIView):
    permission_classes = [perm("api_keys.manage")]

    def post(self, request: Request, pk: Any) -> Response:
        from django.utils import timezone

        k = get_object_or_404(ApiKey, pk=pk)
        if k.revoked_at is None:
            k.revoked_at = timezone.now()
            k.save(update_fields=["revoked_at"])
            audit.record(request.user, "api_key.revoke", "api_key", k.id,
                         f"Revoked API key {k.name} ({k.prefix})")
        return Response(key_body(k))


# ------------------------------------------------------------------ API docs (Admin only)

class SchemaView(SpectacularAPIView):
    permission_classes = [perm("roles.manage")]


class DocsView(SpectacularSwaggerView):
    permission_classes = [perm("roles.manage")]
