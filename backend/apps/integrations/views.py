"""Admin screens' API: webhook integrations, their delivery log, API keys, API docs."""
import uuid

from django.shortcuts import get_object_or_404
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from jinja2 import TemplateError
from jinja2.sandbox import ImmutableSandboxedEnvironment
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import audit
from apps.accounts.permissions import perm
from apps.bookings.models import Booking
from apps.bookings.services import err
from apps.forms.models import Field, Form, FormType

from . import apikeys, webhooks
from .models import ApiKey, Delivery, Integration

TOGGLES = ("include_data", "include_pdf", "include_image_zip", "include_video_zip", "is_active")


def _clean_integration(data: dict, current: Integration | None = None) -> dict:
    """Validated column values from a request body (only what the body carries)."""
    out: dict = {}
    if "form" in data or current is None:
        form_id = data.get("form")
        form = Form.objects.filter(pk=form_id).first() if isinstance(form_id, int) else None
        if form is None or form.type not in (FormType.BOOKING, FormType.CUSTOM):
            raise err("INVALID_FORM", "Choose a booking or inspection form.")
        out["form"] = form
    if "name" in data or current is None:
        name = data.get("name")
        if not isinstance(name, str) or not name.strip() or len(name) > 100:
            raise err("INVALID_NAME", "Give the integration a name (up to 100 characters).")
        out["name"] = name.strip()
    if "url" in data or current is None:
        url = data.get("url")
        reason = webhooks.check_url(url) if isinstance(url, str) and len(url) <= 500 else "bad_url"
        if reason:
            raise err("INVALID_URL", f"This URL cannot be used ({reason}).", reason=reason)
        out["url"] = url
    if "events" in data or current is None:
        events = data.get("events")
        if (not isinstance(events, list) or not events
                or any(e not in webhooks.EVENTS for e in events)):
            raise err("INVALID_EVENTS", "Pick at least one event.", allowed=webhooks.EVENTS)
        out["events"] = [e for e in webhooks.EVENTS if e in events]
    for key in TOGGLES:
        if key in data:
            if not isinstance(data[key], bool):
                raise err("INVALID_TOGGLE", f"{key} must be true or false.")
            out[key] = data[key]
    if "fields" in data:
        fields = data["fields"]
        if not isinstance(fields, list) or not all(isinstance(f, str) for f in fields):
            raise err("INVALID_FIELDS", "fields must be a list of field keys.")
        out["fields"] = sorted(set(fields))
    if "template" in data:
        template = data["template"]
        if not isinstance(template, str) or len(template) > webhooks.MAX_TEMPLATE:
            raise err("INVALID_TEMPLATE", "The template must be text of up to 10,000 characters.")
        try:
            ImmutableSandboxedEnvironment().from_string(template)
        except TemplateError as e:
            raise err("INVALID_TEMPLATE", f"The template has an error: {e}") from e
        out["template"] = template
    return out


def body(i: Integration, secret: str | None = None) -> dict:
    out = {"id": str(i.id), "form": i.form_id, "form_key": i.form.key, "name": i.name,
           "url": i.url, "events": i.events, "include_data": i.include_data,
           "include_pdf": i.include_pdf, "include_image_zip": i.include_image_zip,
           "include_video_zip": i.include_video_zip, "fields": i.fields,
           "template": i.template, "is_active": i.is_active,
           "secret_last4": i.secret[-4:], "created_at": i.created_at}
    if secret:
        out["secret"] = secret                  # shown once, when created or rotated
    return out


def delivery_body(d: Delivery) -> dict:
    return {"id": str(d.id), "integration": str(d.integration_id), "event": d.event,
            "booking": d.booking_uuid, "booking_id": d.booking_ref, "status": d.status,
            "attempts": d.attempts, "response_status": d.response_status, "error": d.error,
            "next_retry_at": d.next_retry_at, "last_attempt_at": d.last_attempt_at,
            "created_at": d.created_at,
            "resent_of": str(d.resent_of_id) if d.resent_of_id else None}


class IntegrationList(APIView):
    permission_classes = [perm("integrations.manage")]

    def get(self, request):
        qs = Integration.objects.select_related("form")
        if request.query_params.get("form", "").isdigit():
            qs = qs.filter(form_id=request.query_params["form"])
        return Response([body(i) for i in qs])

    def post(self, request):
        i = Integration(secret=webhooks.new_secret(), created_by=request.user,
                        **_clean_integration(request.data))
        i.save()
        audit.record(request.user, "integration.create", "integration", i.id,
                     f"Created integration {i.name} for form {i.form.key}")
        return Response(body(i, i.secret), status=status.HTTP_201_CREATED)


class IntegrationDetail(APIView):
    permission_classes = [perm("integrations.manage")]

    def _get(self, pk) -> Integration:
        return get_object_or_404(Integration.objects.select_related("form"), pk=pk)

    def get(self, request, pk):
        return Response(body(self._get(pk)))

    def patch(self, request, pk):
        i = self._get(pk)
        for key, value in _clean_integration(request.data, i).items():
            setattr(i, key, value)
        i.save()
        audit.record(request.user, "integration.update", "integration", i.id,
                     f"Updated integration {i.name}")
        return Response(body(i))

    def delete(self, request, pk):
        i = self._get(pk)
        audit.record(request.user, "integration.delete", "integration", i.id,
                     f"Deleted integration {i.name}")
        i.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class RotateSecret(APIView):
    permission_classes = [perm("integrations.manage")]

    def post(self, request, pk):
        i = get_object_or_404(Integration.objects.select_related("form"), pk=pk)
        i.secret = webhooks.new_secret()
        i.save(update_fields=["secret"])
        audit.record(request.user, "integration.rotate_secret", "integration", i.id,
                     f"Rotated the signing secret of {i.name}")
        return Response(body(i, i.secret))


class EventCatalog(APIView):
    permission_classes = [perm("integrations.manage")]

    def get(self, request):
        return Response(webhooks.EVENTS)


def _booking_for(request, form: Form) -> Booking | None:
    raw = request.data.get("booking")
    if raw:
        try:
            return get_object_or_404(Booking, pk=uuid.UUID(str(raw)))
        except ValueError as e:
            raise ValidationError({"booking": "Not a valid booking id."}) from e
    qs = Booking.objects.all()
    if form.type == FormType.CUSTOM:
        qs = qs.filter(inspection_type=form.inspection_type)
    return qs.order_by("-created_at").first()


class TestSend(APIView):
    """The test button: sends a `test.ping` now, with a real booking's data if there is one."""

    permission_classes = [perm("integrations.manage")]

    def post(self, request, pk):
        i = get_object_or_404(Integration.objects.select_related("form"), pk=pk)
        booking = _booking_for(request, i.form)
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


class RenderSample(APIView):
    """Template preview for the editor: render an unsaved template with a real booking."""

    permission_classes = [perm("integrations.manage")]

    def post(self, request):
        template = request.data.get("template", "")
        form = get_object_or_404(Form, pk=request.data.get("form"))
        booking = _booking_for(request, form)
        i = Integration(form=form, include_data=True, template=template, fields=[])
        d = Delivery(integration=i, event="booking.updated",
                     booking_uuid=str(booking.id) if booking else "",
                     booking_ref=booking.booking_id if booking else "", context={})
        try:
            return Response({"rendered": webhooks.render_template(
                template, webhooks.build_payload(d))})
        except Exception as e:  # noqa: BLE001 - whatever the template does, it is the admin's to fix
            raise err("TEMPLATE_ERROR", f"The template failed: {e}") from e


class DeliveryList(APIView):
    permission_classes = [perm("integrations.manage")]

    def get(self, request, pk):
        i = get_object_or_404(Integration, pk=pk)
        qs = i.deliveries.all()
        for param in ("status", "event"):
            if request.query_params.get(param):
                qs = qs.filter(**{param: request.query_params[param]})
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([delivery_body(d) for d in page or []])


class Resend(APIView):
    """Manual re-send: a new delivery of the same event, built from today's data."""

    permission_classes = [perm("integrations.manage")]

    def post(self, request, pk):
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

def _clean_scope(scope) -> dict:
    """{"forms": {form key: [field keys] or ["*"]}} where every name really exists."""
    if not isinstance(scope, dict) or not isinstance(scope.get("forms"), dict) \
            or not scope["forms"] or set(scope) - {"forms"}:
        raise err("INVALID_SCOPE", 'scope must look like {"forms": {"<form key>": ["<field>"]}}.')
    out: dict = {}
    for key, fields in scope["forms"].items():
        form = Form.objects.filter(key=key, type__in=[FormType.BOOKING, FormType.CUSTOM],
                                   is_active=True).first()
        if form is None:
            raise err("INVALID_SCOPE", f"'{key}' is not an active booking or inspection form.")
        if fields == ["*"]:
            out[key] = ["*"]
            continue
        if not isinstance(fields, list) or not fields or not all(
                isinstance(f, str) for f in fields):
            raise err("INVALID_SCOPE", f"List the field keys for '{key}', or [\"*\"].")
        known = set(Field.objects.filter(version__form=form, key__in=fields)
                    .values_list("key", flat=True))
        if set(fields) - known:
            raise err("INVALID_SCOPE", f"Unknown fields for '{key}': "
                      f"{', '.join(sorted(set(fields) - known))}.")
        out[key] = sorted(set(fields))
    return {"forms": out}


def key_body(k: ApiKey, full_key: str | None = None) -> dict:
    out = {"id": str(k.id), "name": k.name, "prefix": k.prefix, "scope": k.scope,
           "allow_delete": k.allow_delete, "revoked_at": k.revoked_at,
           "last_used_at": k.last_used_at, "created_at": k.created_at}
    if full_key:
        out["key"] = full_key                   # shown once
    return out


class ApiKeyList(APIView):
    permission_classes = [perm("api_keys.manage")]

    def get(self, request):
        return Response([key_body(k) for k in ApiKey.objects.all()])

    def post(self, request):
        name = request.data.get("name")
        if not isinstance(name, str) or not name.strip() or len(name) > 100:
            raise err("INVALID_NAME", "Give the key a name (up to 100 characters).")
        allow = request.data.get("allow_delete", False)
        if not isinstance(allow, bool):
            raise err("INVALID_TOGGLE", "allow_delete must be true or false.")
        scope = _clean_scope(request.data.get("scope"))
        key, prefix, hashed = apikeys.generate()
        k = ApiKey.objects.create(name=name.strip(), prefix=prefix, key_hash=hashed, scope=scope,
                                  allow_delete=allow, created_by=request.user)
        audit.record(request.user, "api_key.create", "api_key", k.id,
                     f"Created API key {k.name} ({k.prefix}){' with DELETE' if allow else ''}")
        return Response(key_body(k, key), status=status.HTTP_201_CREATED)


class ApiKeyDetail(APIView):
    permission_classes = [perm("api_keys.manage")]

    def get(self, request, pk):
        return Response(key_body(get_object_or_404(ApiKey, pk=pk)))

    def patch(self, request, pk):
        k = get_object_or_404(ApiKey, pk=pk)
        if k.revoked_at is not None:
            raise err("KEY_REVOKED", "A revoked key cannot be changed.", 409)
        if "name" in request.data:
            name = request.data["name"]
            if not isinstance(name, str) or not name.strip() or len(name) > 100:
                raise err("INVALID_NAME", "Give the key a name (up to 100 characters).")
            k.name = name.strip()
        if "scope" in request.data:
            k.scope = _clean_scope(request.data["scope"])
        if "allow_delete" in request.data:
            if not isinstance(request.data["allow_delete"], bool):
                raise err("INVALID_TOGGLE", "allow_delete must be true or false.")
            k.allow_delete = request.data["allow_delete"]
        k.save()
        audit.record(request.user, "api_key.update", "api_key", k.id,
                     f"Updated API key {k.name} ({k.prefix}); delete "
                     f"{'allowed' if k.allow_delete else 'off'}")
        return Response(key_body(k))


class ApiKeyRevoke(APIView):
    permission_classes = [perm("api_keys.manage")]

    def post(self, request, pk):
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
