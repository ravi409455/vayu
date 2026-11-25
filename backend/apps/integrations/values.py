"""What an integration can send: the picker's list of values and the filling of {{ref}} tokens.

One string syntax is used in the URL path, query, headers and body values: text with `{{ref}}`
tokens. A value that is exactly one token keeps its type; anything else becomes text."""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

# {{ref}}, or {{ref | text}} to send the value as text
TOKEN = re.compile(r"\{\{\s*([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_\-]+)+)(\s*\|\s*text)?\s*\}\}")
MAX_NODES, MAX_HEADERS, MAX_QUERY, MAX_DEPTH = 500, 20, 30, 8

GROUPS = {"booking": "Booking form", "start": "Check-in (start)", "inspection": "Inspection",
          "end": "Wrap-up (end)", "job": "Booking details", "result": "Results", "link": "Links",
          "event": "Event"}
JOB = {"job.booking_id": ("Booking ID", "text"),
       "job.previous_booking_id": ("Previous Booking ID", "text"),
       "job.id": ("Internal id", "text"), "job.type": ("Inspection type", "text"),
       "job.stage": ("Stage", "text"), "job.city": ("City", "text"),
       "job.expert": ("Expert", "text"), "job.created_at": ("Created at", "datetime"),
       "job.submitted_at": ("Submitted at", "datetime"), "job.revision": ("Revision", "number")}
# a field's picker type; photos, videos, files, signatures and pictures are links, not values
HIDDEN = {"photo", "video", "file", "signature", "image"}
TYPES = {"number": "number", "currency": "number", "rating": "number", "yes_no": "boolean",
         "derived": "boolean", "date": "date", "datetime": "datetime", "multi_choice": "list"}

_BASE = {"booking", "job", "event"}
_START = _BASE | {"start"}
_DONE = _START | {"inspection", "end", "result"}
_ALL = _DONE | {"zip", "pdf"}
AVAILABLE = {"booking.created": _BASE, "booking.updated": _ALL, "booking.deleted": {"event"},
             "inspection.started": _START, "inspection.submitted": _DONE,
             "media.completed": _DONE | {"zip"}, "pdf.ready": _ALL,
             "alert.conflict": _BASE, "alert.stuck_upload": _BASE}


class MissingPathValue(ValueError):
    pass


# ------------------------------------------------------------------ the picker's list

def _live(form, override: dict):
    from apps.bookings.submissions import latest_published

    return override[form.id] if form.id in override else latest_published(form)


def versions(form, override: dict | None = None) -> dict:
    """part -> the version whose fields the picker offers (the latest published one)."""
    from apps.forms.models import Form, FormType

    override = override or {}
    booking = Form.objects.filter(type=FormType.BOOKING).first()
    out: dict = {"booking": _live(booking, override) if booking else None}
    if form.type == FormType.CUSTOM:
        out["inspection"] = _live(form, override)
        for part, ftype in (("start", FormType.START), ("end", FormType.END)):
            sys_form = Form.objects.filter(type=ftype).first()
            used = out["inspection"] is None or getattr(out["inspection"], f"use_{part}")
            out[part] = _live(sys_form, override) if sys_form and used else None
    return out


def _fields(version) -> list:
    from apps.forms.models import Field

    if version is None:
        return []
    return list(Field.objects.filter(version=version).order_by(
        "section__page__order", "section__order", "order", "id"))


def catalogue(form, event: str | None = None, override: dict | None = None) -> list[dict]:
    """[{group, ref, label, type}] for this form. `event` hides what can never be filled for it;
    None lists everything (used to find values whose field has gone)."""
    from apps.forms.models import FormType

    if event == "booking.deleted":
        keep = AVAILABLE[event]
    elif event is None:
        keep = _ALL
    else:
        keep = AVAILABLE.get(event, _ALL)
    if form.type == FormType.BOOKING:
        keep = keep & (_BASE | {"event"})
    vers = versions(form, override)
    out: list[dict] = []

    def add(group: str, ref: str, label: str, type_: str) -> None:
        out.append({"group": group, "ref": ref, "label": label, "type": type_})

    for part in ("booking", "start", "inspection", "end"):
        if part not in keep:
            continue
        for f in _fields(vers.get(part)):
            if f.type not in HIDDEN:
                add(part, f"{part}.{f.key}", f.label, TYPES.get(f.type, "text"))
    if "job" in keep:
        for ref, (label, type_) in JOB.items():
            add("job", ref, label, type_)
    else:                                     # a deleted booking: its ID only
        add("job", "job.booking_id", JOB["job.booking_id"][0], "text")
    if "result" in keep and vers.get("inspection") is not None:
        add("result", "result.overall", "Overall rating", "text")
        add("result", "result.average", "Average rating", "number")
        add("result", "result.ratings", "Ratings by category", "list")
        for c in (vers["inspection"].rating_config or {}).get("categories", []):
            add("result", f"result.rating.{c['key']}", f"Rating: {c['label']}", "number")
        add("result", "result.key_checks", "Key Check results", "list")
        for kc in vers["inspection"].key_checks or []:
            add("result", f"result.key_check.{kc['key']}", f"Key Check: {kc['label']}",
                {"number": "number", "date": "date"}.get(kc["type"], "text"))
        add("result", "result.defects", "Fields with defects", "list")
    if "pdf" in keep and form.type == FormType.CUSTOM:
        add("link", "link.pdf", "PDF link", "text")
    if "zip" in keep and form.type == FormType.CUSTOM:
        add("link", "link.image_zip", "Image ZIP link", "text")
        add("link", "link.video_zip", "Video ZIP link", "text")
    for part in ("start", "inspection", "end"):
        if part in keep:
            for f in _fields(vers.get(part)):
                if f.type == "photo":
                    add("link", f"link.photos.{f.key}", f"{f.label} (photo links)", "list")
    add("event", "event.name", "Event name", "text")
    add("event", "event.delivery", "Delivery id", "text")
    add("event", "event.time", "Event time", "datetime")
    if event in (None, "booking.updated"):
        add("event", "event.changed_fields", "Changed fields", "list")
    if event is None or (event or "").startswith("alert."):
        add("event", "event.alert", "Alert code", "text")
    return out


# ------------------------------------------------------------------ strings with {{ref}}

def check_syntax(text: str) -> bool:
    """False when a '{{' or '}}' is left that is not a whole {{ref}}."""
    rest = TOKEN.sub("", text)
    return "{{" not in rest and "}}" not in rest


def refs_in(text: str) -> list[str]:
    return [m.group(1) for m in TOKEN.finditer(text)]


def _kc_value(kc: dict, scores: dict) -> Any:
    """A Key Check's value for an integration: a number when it is a Number one that reads as a
    number, else the text."""
    text = ((scores.get("key_checks") or {}).get(kc["key"]) or {}).get("value")
    if kc["type"] == "number" and text:
        try:
            n = float(text.replace(",", ""))
            return int(n) if n.is_integer() else n
        except ValueError:
            pass
    return text


def text_of(v: Any, sep: str = ", ") -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, list):
        return sep.join(text_of(x, sep) for x in v if x is not None)
    if isinstance(v, dict):
        return json.dumps(v, separators=(",", ":"))
    return str(v)


def render(text: str, get: Callable[[str], Any], *, as_text: bool = False, sep: str = ", ",
           encode: bool = False) -> Any:
    """Fill the tokens. Exactly one token and nothing else: the value keeps its type (null when
    empty) unless `as_text`. `encode` is for the URL path: values are percent-encoded and an empty
    one is an error."""
    one = TOKEN.fullmatch(text)
    as_text = as_text or bool(one and one.group(2))
    if one and not as_text and not encode:
        v = get(one.group(1))
        return None if v == "" else v

    def fill(m: re.Match) -> str:
        s = text_of(get(m.group(1)), sep)
        if encode:
            if not s:
                raise MissingPathValue(m.group(1))
            return quote(s, safe="")
        return s

    out = TOKEN.sub(fill, text)
    if one and as_text and get(one.group(1)) is None:
        return None
    return out


def render_json(node: Any, get: Callable[[str], Any]) -> Any:
    """A custom body is a JSON document: every string in it is filled like any other text (a
    string that is exactly one {{ref}} becomes the value itself); other JSON stays as it is."""
    if isinstance(node, str):
        return render(node, get)
    if isinstance(node, dict):
        return {k: render_json(v, get) for k, v in node.items()}
    if isinstance(node, list):
        return [render_json(v, get) for v in node]
    return node


def json_strings(node: Any) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for v in node.values() for s in json_strings(v)]
    if isinstance(node, list):
        return [s for v in node for s in json_strings(v)]
    return []


def used_refs(integ) -> set[str]:
    texts = [integ.url, *(q.get("value", "") for q in integ.query),
             *(h.get("value", "") for h in integ.headers)]
    if integ.body_mode == "custom":
        texts += json_strings(integ.body)
    return {r for t in texts for r in refs_in(t)}


def broken_refs(integ, override: dict | None = None) -> list[str]:
    """Values the integration uses whose field is not in the form's live version any more."""
    have = {e["ref"] for e in catalogue(integ.form, None, override)}
    broken = {r for r in used_refs(integ) if r not in have}
    if integ.body_mode == "standard" and integ.include_data and integ.fields:
        keys = {f.key for v in versions(integ.form, override).items()
                if v[0] in ("booking", "inspection") for f in _fields(v[1])}
        broken |= {f"field.{k}" for k in integ.fields if k not in keys}
    return sorted(broken)


def publish_warnings(version, *, published: bool) -> list[dict]:
    """Integrations whose values the version breaks. `published`: the version is live already,
    so "before" is the one it replaced; otherwise it is a draft that would replace the live one."""
    from apps.forms.models import VersionStatus

    from .models import Integration

    if published:
        prev = version.form.versions.filter(
            status=VersionStatus.PUBLISHED, number__lt=version.number).order_by("-number").first()
        before, after = {version.form_id: prev}, {}
    else:
        before, after = {}, {version.form_id: version}
    out = []
    for i in Integration.objects.select_related("form"):
        if not used_refs(i) and not (i.fields and i.body_mode == "standard"):
            continue
        new = sorted(set(broken_refs(i, after)) - set(broken_refs(i, before)))
        if new:
            out.append({"code": "INTEGRATION_FIELD_MISSING", "integration": str(i.id),
                        "name": i.name, "keys": new,
                        "message": f"Integration '{i.name}' uses {', '.join(new)}, which this "
                                   "version does not have; it will send nothing for it."})
    return out


# ------------------------------------------------------------------ a job's values

def sample(type_: str, ref: str) -> Any:
    if type_ == "number":
        return 42
    if type_ == "boolean":
        return True
    if type_ == "date":
        return "2026-01-15"
    if type_ == "datetime":
        return "2026-01-15T10:30:00+05:30"
    if type_ == "list":
        return ["sample 1", "sample 2"]
    return {"job.booking_id": "SAMPLE-001"}.get(ref, "sample")


class Resolver:
    """Looks up {{ref}} values for one delivery, only when a token asks for them.

    mode "send": real values. "preview": the same, but ZIP links are examples (nothing is built).
    "sample": made-up values from each value's type (a form without jobs)."""

    def __init__(self, d, mode: str = "send", types: dict[str, str] | None = None):
        from apps.bookings.models import Booking

        self.d, self.mode, self.types = d, mode, types or {}
        self.booking = Booking.objects.filter(pk=d.booking_uuid).first() if d.booking_uuid else None
        # nothing of a deleted (or vanished) booking leaves except its ID
        self.limited = self.booking is None or d.event == "booking.deleted"
        self._cache: dict[str, Any] = {}
        self._insp: Any = False

    def get(self, ref: str) -> Any:
        if ref not in self._cache:
            v = self._get(ref)
            self._cache[ref] = None if v == "" else v
        return self._cache[ref]

    def _booking(self):
        assert self.booking is not None      # callers run only when the job still exists
        return self.booking

    def inspection(self):
        if self._insp is False:
            b = self.booking
            # before any submission, the running draft (inspection.started); never past a
            # conflict, where nothing counts until Ops choose
            self._insp = (b.counted_inspection() or (
                None if b.conflict else b.inspections.order_by("-created_at").first())
            ) if b else None
        return self._insp

    def _get(self, ref: str) -> Any:
        head, _, rest = ref.partition(".")
        if head == "event":
            return self._event(rest)
        if self.mode == "sample":
            return sample(self.types.get(ref, "text"), ref)
        if self.limited:
            return self.d.booking_ref if ref == "job.booking_id" else None
        if head == "job":
            return self._job(rest)
        if head == "booking":
            return self._booking().answers.get(rest)
        if head in ("start", "inspection", "end"):
            return self._answer(head, rest)
        if head == "result":
            return self._result(rest)
        if head == "link":
            return self._link(rest)
        return None

    def _event(self, name: str) -> Any:
        d = self.d
        return {"name": d.event, "delivery": str(d.id), "time": d.created_at.isoformat(),
                "changed_fields": d.context.get("changed_keys"),
                "alert": d.context.get("alert")}.get(name)

    def _job(self, name: str) -> Any:
        b, insp = self._booking(), None
        if name == "previous_booking_id":
            return (self.d.context.get("booking_id_change") or [None])[0]
        if name == "submitted_at":
            insp = self.inspection()
            return insp.submitted_at.isoformat() if insp and insp.submitted_at else None
        if name == "revision":
            return self.d.context.get("revision")
        if name == "expert":
            return (b.assigned_expert.name or b.assigned_expert.username) if b.assigned_expert \
                else None
        if name == "created_at":
            return b.created_at.isoformat()
        return {"booking_id": b.booking_id, "id": str(b.id), "type": b.inspection_type,
                "stage": b.stage, "city": b.city}.get(name)

    def _answer(self, part: str, key: str) -> Any:
        from apps.forms.models import Field

        insp = self.inspection()
        if insp is None:
            return None
        version = {"inspection": insp.form_version, "start": insp.start_version,
                   "end": insp.end_version}[part]
        ftype = Field.objects.filter(version=version, key=key).values_list(
            "type", flat=True).first() if version else None
        scores = insp.scores or {}
        if ftype == "derived":
            return scores.get("derived", {}).get(key)
        if ftype == "rating":
            return scores.get("fields", {}).get(key)
        v = (insp.answers.get(part) or {}).get(key)
        if ftype == "gps" and isinstance(v, dict):
            return f"{v.get('lat')},{v.get('lng')}"
        return v

    def _result(self, name: str) -> Any:
        from apps.forms.models import Field

        insp = self.inspection()
        s = (insp.scores or {}) if insp else {}
        if not s:
            return None
        if name == "overall":
            return s.get("overall", {}).get("word")
        if name == "average":
            return s.get("overall", {}).get("average")
        if name == "defects":
            return s.get("defects", [])
        if name == "ratings":
            labels = {c["key"]: c["label"]
                      for c in (insp.form_version.rating_config or {}).get("categories", [])}
            return [{"category": labels.get(k, k), "rating": r["value"]}
                    for k, r in s.get("ratings", {}).items()]
        if name == "key_checks" and insp.form_version.key_checks:
            return [{"name": kc["label"], "value": _kc_value(kc, s)}
                    for kc in insp.form_version.key_checks]
        if name.startswith("key_check."):
            kc = next((k for k in insp.form_version.key_checks or [] if k["key"] == name[10:]),
                      None)
            return _kc_value(kc, s) if kc else None
        if name == "key_checks":                  # forms from before Key Checks were a list
            derived = s.get("derived", {})
            return [{"name": f.label, "result": derived.get(f.key)} for f in
                    Field.objects.filter(version=insp.form_version, type="derived").order_by("id")]
        if name.startswith("rating."):
            return s.get("ratings", {}).get(name[7:], {}).get("value")
        return None

    def _link(self, name: str) -> Any:
        from django.conf import settings

        from apps.media import storage as media_storage
        from apps.media import zips
        from apps.media.models import MediaAsset
        from apps.reports.models import Report

        b, ttl = self._booking(), settings.WEBHOOK_LINK_DAYS * 86400
        if name == "pdf":
            report = Report.objects.filter(booking=b, status="ready").first()
            return (media_storage.presign_get(report.key, report.filename, ttl) if report
                    else (f"{settings.PUBLIC_BASE_URL}/example/report.pdf"
                          if self.mode == "preview" else None))
        if name in ("image_zip", "video_zip"):
            kind = name[:5]
            if self.mode == "preview":
                return f"{settings.PUBLIC_BASE_URL}/zip/example-{kind}-link"
            has = MediaAsset.objects.filter(booking=b, status="verified",
                                            kind__in=zips.KIND_TYPES[kind]).exists()
            z = zips.request_zip(b, kind) if has else None
            return f"{settings.PUBLIC_BASE_URL}/zip/{zips.token_for(z.id)}" if z else None
        if name.startswith("photos."):
            return [media_storage.presign_get(a.key, None, ttl) for a in MediaAsset.objects.filter(
                booking=b, status="verified", kind="photo",
                field_key=name[7:]).order_by("created_at")]
        return None
