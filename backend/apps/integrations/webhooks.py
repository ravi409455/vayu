"""Webhooks: which events go where, what the body holds, how it is signed and retried.

Delivery rows hold metadata only. The body is built again from current data each time it is
sent, so no customer value ever sits in the delivery log."""
import hashlib
import hmac
import ipaddress
import json
import logging
import secrets
import socket
from datetime import timedelta
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.utils import timezone
from jinja2 import TemplateError
from jinja2.sandbox import ImmutableSandboxedEnvironment
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool

from apps.core import tasks as core_tasks

from .models import Delivery, Integration

logger = logging.getLogger(__name__)

EVENTS = ["booking.created", "booking.updated", "booking.deleted", "inspection.started",
          "inspection.submitted", "media.completed", "pdf.ready", "alert.conflict",
          "alert.stuck_upload"]
# internal event name -> the public event it becomes
PUBLIC = {"booking.created": "booking.created", "booking.updated": "booking.updated",
          "booking.assigned": "booking.updated", "booking.deleted": "booking.deleted",
          "inspection.started": "inspection.started",
          "inspection.submitted": "inspection.submitted", "media.completed": "media.completed",
          "pdf.ready": "pdf.ready", "alert.conflict": "alert.conflict",
          "alert.type_change_rejected": "alert.conflict",
          "alert.stuck_upload": "alert.stuck_upload"}
MAX_TEMPLATE = 10_000
MAX_BODY = 1_000_000


def new_secret() -> str:
    return "whsec_" + secrets.token_urlsafe(24)


# ------------------------------------------------------------------ address safety

def resolve(host: str) -> list[str]:  # pragma: no cover - real DNS; tests replace it
    return sorted({str(i[4][0]) for i in socket.getaddrinfo(host, None)})


def check_url(url: str) -> str | None:
    """A reason code if this URL must not be called, else None. Webhooks may only leave for
    public addresses, so a URL can never be used to reach our own network."""
    parts = urlparse(url)
    if parts.scheme != "https" and not (parts.scheme == "http" and settings.WEBHOOK_ALLOW_HTTP):
        return "https_required"
    if not parts.hostname or parts.username or parts.password:
        return "bad_url"
    try:
        addresses = resolve(parts.hostname)
    except OSError:
        return "host_not_found"
    if not settings.WEBHOOK_ALLOW_PRIVATE and not all(
            ipaddress.ip_address(a).is_global for a in addresses):
        return "blocked_address"
    return None


class BlockedAddress(OSError):
    pass


class _PeerGuard:
    """Checks the address actually connected to, so a DNS answer that changes between our check
    and the connection (DNS rebinding) cannot reach a private address."""

    def _new_conn(self):
        sock = super()._new_conn()  # type: ignore[misc]
        if not settings.WEBHOOK_ALLOW_PRIVATE and not ipaddress.ip_address(
                sock.getpeername()[0]).is_global:
            sock.close()
            raise BlockedAddress("blocked_address")
        return sock


class GuardedHTTPConnection(_PeerGuard, HTTPConnection):
    pass


class GuardedHTTPSConnection(_PeerGuard, HTTPSConnection):
    pass


class GuardedHTTPPool(HTTPConnectionPool):
    ConnectionCls = GuardedHTTPConnection


class GuardedHTTPSPool(HTTPSConnectionPool):
    ConnectionCls = GuardedHTTPSConnection


class GuardedAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)
        self.poolmanager.pool_classes_by_scheme = {"http": GuardedHTTPPool,
                                                   "https": GuardedHTTPSPool}


def session() -> requests.Session:
    s = requests.Session()
    s.mount("http://", GuardedAdapter())
    s.mount("https://", GuardedAdapter())
    return s


# ------------------------------------------------------------------ routing

def _context(public: str, payload: dict) -> dict:
    """The few facts a delivery needs later. Values are left out on purpose, except the old and
    new Booking ID (an edited ID must reach the other system)."""
    ctx: dict = {}
    changes = payload.get("changes") or {}
    if changes:
        ctx["changed_keys"] = sorted(changes)
        if "booking_id" in changes:
            ctx["booking_id_change"] = changes["booking_id"]
    if payload.get("expert") is not None:
        ctx["changed_keys"] = sorted({*ctx.get("changed_keys", []), "assigned_expert"})
    for key in ("inspection", "revision", "media", "reason"):
        if payload.get(key) is not None:
            ctx[key] = payload[key]
    if public == "alert.conflict":
        ctx["alert"] = payload.get("code") or "TYPE_CHANGE_REJECTED"
    return ctx


def targets(booking, public: str) -> list[Integration]:
    """Integrations of the booking form (booking events) and of the inspection form that handles
    this booking's type (every event) that subscribed to this event."""
    from django.db.models import Q

    from apps.forms.models import FormKind

    rows = Integration.objects.filter(is_active=True, form__is_active=True).select_related("form")
    q = Q(form__kind=FormKind.BOOKING) & Q(events__contains=[public]) \
        if public.startswith("booking.") else Q(pk__in=[])
    if booking is not None:
        q |= (Q(form__kind=FormKind.INSPECTION, form__inspection_type=booking.inspection_type)
              & Q(events__contains=[public]))
    return list(rows.filter(q))


def on_event(name: str, payload: dict) -> None:
    from apps.bookings.models import Booking

    public = PUBLIC.get(name)
    if public is None or not payload.get("booking"):
        return
    booking = Booking.objects.filter(pk=payload["booking"]).first()
    ref = payload.get("booking_id") or (booking.booking_id if booking else "")
    for integration in targets(booking, public):
        d = Delivery.objects.create(
            integration=integration, event=public, booking=booking,
            booking_uuid=str(payload["booking"]), booking_ref=ref,
            context=_context(public, payload))
        send_later(d)


def send_later(d: Delivery) -> None:
    from .tasks import deliver

    core_tasks.after_commit(lambda: deliver.delay(str(d.id)))


# ------------------------------------------------------------------ the body

def _scoped(answers: dict, allowed: list) -> dict:
    return {k: v for k, v in (answers or {}).items() if not allowed or k in allowed}


def build_payload(d: Delivery) -> dict:
    from apps.bookings.models import Booking
    from apps.media import storage as media_storage
    from apps.media import zips
    from apps.media.models import MediaAsset
    from apps.reports.models import Report

    integ = d.integration
    body: dict = {"event": d.event, "delivery": str(d.id),
                  "occurred_at": d.created_at.isoformat(),
                  "booking": {"id": d.booking_uuid, "booking_id": d.booking_ref}}
    for key in ("changed_keys", "inspection", "revision", "alert", "reason"):
        if key in d.context:
            body[key] = d.context[key]
    if "booking_id_change" in d.context:
        old, new = d.context["booking_id_change"]
        body["booking_id_change"] = {"from": old, "to": new}
    booking = Booking.objects.filter(pk=d.booking_uuid).first() if d.booking_uuid else None
    if booking is None or d.event == "booking.deleted":     # nothing of a deleted booking leaves
        return body
    body["booking"]["booking_id"] = booking.booking_id
    insp = booking.inspections.filter(status="submitted").order_by("-submitted_at").first()
    if integ.include_data:
        body["data"] = {"booking": _scoped(booking.answers, integ.fields),
                        "inspection": _scoped(((insp.answers.get("inspection") or {})
                                               if insp else {}), integ.fields)}
    if integ.include_pdf:
        report = Report.objects.filter(booking=booking, status="ready").first()
        body["pdf_url"] = (media_storage.presign_get(
            report.key, report.filename, settings.WEBHOOK_LINK_DAYS * 86400) if report else None)
    for flag, kind in ((integ.include_image_zip, "image"), (integ.include_video_zip, "video")):
        if flag:
            has = MediaAsset.objects.filter(booking=booking, status="verified",
                                           kind__in=zips.KIND_TYPES[kind]).exists()
            z = zips.request_zip(booking, kind) if has else None
            body[f"{kind}_zip_url"] = (f"{settings.PUBLIC_BASE_URL}/api/v1/zips/"
                                       f"{zips.token_for(z.id)}" if z else None)
    return body


def render_template(template: str, body: dict) -> str:
    """Admin's {{ field.key }} template, rendered in a sandbox with a fixed, small context."""
    if len(template) > MAX_TEMPLATE:
        raise TemplateError("template too long")
    env = ImmutableSandboxedEnvironment(autoescape=False)
    data = body.get("data") or {}
    fields = {**data.get("booking", {}), **data.get("inspection", {})}
    context = {"event": body["event"], "booking": body["booking"], "field": fields,
               "pdf_url": body.get("pdf_url"), "image_zip_url": body.get("image_zip_url"),
               "video_zip_url": body.get("video_zip_url"),
               "changed_keys": body.get("changed_keys", [])}
    out = env.from_string(template).render(**context)
    if len(out) > MAX_BODY:
        raise TemplateError("rendered body too large")
    return out


def encode(d: Delivery) -> tuple[bytes, str]:
    """(raw body bytes, content type). Raises on a broken template."""
    body = build_payload(d)
    if d.integration.template:
        text = render_template(d.integration.template, body)
        try:
            json.loads(text)
            kind = "application/json"
        except ValueError:
            kind = "text/plain; charset=utf-8"
        return text.encode(), kind
    return json.dumps(body, separators=(",", ":"), default=str).encode(), "application/json"


def sign(secret: str, raw: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


# ------------------------------------------------------------------ sending

def _finish(d: Delivery, status: str, error: str = "", http: int | None = None) -> None:
    d.status, d.error, d.response_status = status, error, http
    d.next_retry_at = None
    d.save()


def attempt(d: Delivery) -> Delivery:
    """One send. Retry rules: network errors, timeouts, 429 and 5xx are retried on the schedule
    (1m, 5m, 30m, 2h, 6h, 12h); any other answer is final."""
    integ = d.integration
    d.attempts += 1
    d.last_attempt_at = timezone.now()
    if not integ.is_active:
        _finish(d, "failed", "integration_disabled")
        return d
    try:
        raw, content_type = encode(d)
    except Exception:  # noqa: BLE001 - a bad template must never kill the worker
        logger.warning("Webhook body failed for delivery %s", d.id)
        _finish(d, "failed", "template_failed")
        return d
    reason = check_url(integ.url)
    if reason:
        _finish(d, "failed", reason)
        return d
    headers = {"Content-Type": content_type, "X-Vayu-Event": d.event,
               "X-Vayu-Delivery": str(d.id), "X-Vayu-Signature": sign(integ.secret, raw),
               "User-Agent": "Vayu-Webhooks/1"}
    try:
        with session() as s:
            r = s.post(integ.url, data=raw, headers=headers, timeout=settings.WEBHOOK_TIMEOUT,
                       allow_redirects=False)
    except requests.Timeout:
        return _retry(d, "timeout", None)
    except requests.RequestException as e:
        if "blocked_address" in str(e):          # the connection went to a private address
            _finish(d, "failed", "blocked_address")
            return d
        return _retry(d, "connection_error", None)
    if 200 <= r.status_code < 300:
        _finish(d, "success", "", r.status_code)
    elif r.status_code == 429 or r.status_code >= 500:
        return _retry(d, f"http_{r.status_code}", r.status_code)
    else:
        _finish(d, "failed", f"http_{r.status_code}", r.status_code)
    return d


def _retry(d: Delivery, error: str, http: int | None) -> Delivery:
    schedule = settings.WEBHOOK_RETRY_SECONDS
    if d.attempts > len(schedule):
        _finish(d, "failed", "retries_exhausted", http)
        return d
    d.status, d.error, d.response_status = "retrying", error, http
    d.next_retry_at = timezone.now() + timedelta(seconds=schedule[d.attempts - 1])
    d.save()
    return d
