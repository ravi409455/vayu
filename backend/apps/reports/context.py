"""Everything a report shows, worked out from the stored data: which pages and parts appear, each
row's label, answer and colour, and which photos go in each grid. Missing values never raise."""
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from django.utils import timezone

from apps.bookings.models import Booking, Inspection
from apps.bookings.services import booking_form_version
from apps.forms.fieldtypes import NOT_VALUES
from apps.forms.models import PARTS, Field, MasterListItem, Page, Section
from apps.forms.rules import evaluate_form, spec_from_version, truthy

from . import placeholders
from .definition import field_ref

MEDIA = NOT_VALUES                          # the field-type registry
# the option keys that mean "Not able to check": the demo option sets' and the real (Clappia)
# forms', where the answer "Not Able to Check" becomes not_able_to_check (C-02)
NOT_CHECKED = {"not_checked", "not_able_to_check"}


NOT_POINTS = ("rating", "derived", "image", "form_choice")    # never something the expert records


def _ops_only(f: Field) -> bool:
    """A question of a section (or page) the form hides from experts while they inspect."""
    for layer in (f.access, f.section.access, f.section.page.access):
        level = ((layer or {}).get("expert") or {}).get("in_progress")
        if level is not None:
            return level == "hidden"
    return False


def _as_list(value) -> list:
    return value if isinstance(value, list) else [value]
NOT_ROWS = MEDIA | {"form_choice"}          # never a row of a table


def _label(list_key: str, item_key: str) -> str:
    return (MasterListItem.objects.filter(list__key=list_key, key=item_key)
            .values_list("label", flat=True).first() or str(item_key))


def _tone(option: dict) -> str:
    if option.get("tone"):
        return option["tone"]
    if not option.get("is_defect"):
        return "ok"
    return "warn" if option.get("severity", "minor") == "minor" else "bad"


RANK = {"ok": 0, "muted": 1, "warn": 2, "bad": 3}


def display(f: Field | None, value: Any) -> tuple[str, str | None, bool]:
    """(text, tone, is a problem) of one answer; text '' when there is nothing to show."""
    if f is None or value is None or value == "" or value == []:
        return "", None, False
    t, c = f.type, f.config
    if t in ("single_choice", "multi_choice"):
        options = {o["key"]: o for o in c.get("options", [])}
        chosen = [options.get(k, {"key": k, "label": k}) for k in
                  (value if isinstance(value, list) else [value])]
        # a check (its answers carry colours or mark problems) is coloured; a plain fact is not
        is_check = any("tone" in o or o.get("is_defect") for o in options.values())
        tone = max((_tone(o) for o in chosen), key=RANK.__getitem__) if is_check else None
        return ", ".join(o["label"] for o in chosen), tone, any(o.get("is_defect") for o in chosen)
    if t == "yes_no":
        return ("Yes" if value else "No"), None, False
    if t == "master_list":
        return _label(c.get("list", ""), value), None, False
    if t == "user_picker":
        from apps.accounts.models import User

        u = User.objects.filter(pk=value).first()
        return (u.name or u.username if u else ""), None, False
    if t == "number":
        n = f"{value:g}" if isinstance(value, float) else str(value)
        return (f"{n} {c['unit']}" if c.get("unit") else n), None, False
    if t == "currency":
        return (f"₹{value:,.2f}" if value % 1 else f"₹{int(value):,}"), None, False
    if t == "date":
        return date.fromisoformat(value).strftime("%d-%m-%Y"), None, False
    if t == "datetime":
        return datetime.fromisoformat(value).strftime("%d-%m-%Y %H:%M"), None, False
    if t == "gps":
        return f"{value['lat']:.5f}, {value['lng']:.5f}", None, False
    if t in MEDIA:
        return "", None, False
    if t == "derived":                         # a Key Check: true means an issue was found
        return (c.get("true_label", "Yes") if value else c.get("false_label", "No"),
                "bad" if value else "ok", bool(value))
    if t == "rating":
        return f"{value}/5", None, False
    return str(value), None, False


@dataclass
class Cell:
    text: str
    tone: str | None = None
    problem: bool = False


@dataclass
class Source:
    """Answers, fields and visibility of every form of one inspection."""

    booking: Booking
    insp: Inspection
    revision: int = 0
    token: str = ""
    fields: dict[str, dict[str, Field]] = field(default_factory=dict)
    answers: dict[str, dict] = field(default_factory=dict)
    visible: dict[str, bool] = field(default_factory=dict)
    defects: list[str] = field(default_factory=list)
    version: Any = None
    _values: dict | None = None
    _hidden: set[str] | None = None

    def __post_init__(self):
        scores = self.insp.scores or {}
        self.answers = {"booking": self.booking.answers,
                        **{p: dict(self.insp.answers.get(p) or {}) for p in PARTS}}
        self.answers["inspection"].update({k: v for k, v in scores.get("derived", {}).items()})
        self.answers["inspection"].update(scores.get("fields", {}))
        versions = (("booking", booking_form_version()), *self.insp.pinned().items())
        for kind, version in versions:
            self.fields[kind] = ({f.key: f for f in Field.objects.filter(version=version)
                                  .select_related("section__page")} if version else {})
        version = self.insp.form_version
        result = evaluate_form(spec_from_version(version), self.answers,
                               timezone.localdate().isoformat())
        self.visible = result.visible
        self.defects = [d.split(".", 1)[1] for d in result.defects]
        self.version = version

    # -------------------------------------------------------------- values
    def get_field(self, ref: str) -> Field | None:
        form, key = field_ref(ref)
        return self.fields.get(form, {}).get(key)

    @property
    def customer_hidden(self) -> set[str]:
        """Fields marked "Hide from customer": never printed or linked (apps.media.services)."""
        if self._hidden is None:
            from apps.media.services import customer_hidden
            self._hidden = customer_hidden(self.booking)
        return self._hidden

    def shown(self, ref: str) -> bool:
        form, key = field_ref(ref)
        return form != "inspection" or self.visible.get(key, True)

    def key_checks(self) -> dict[str, str]:
        """Key Checks the report may show (Admin can leave one out): key -> value."""
        values = (self.insp.scores or {}).get("key_checks") or {}
        return {kc["key"]: (values.get(kc["key"]) or {}).get("value", "")
                for kc in self.version.key_checks or [] if kc.get("in_report", True)}

    def cell(self, ref: str) -> Cell:
        form, key = field_ref(ref)
        if form == "check":
            return Cell(self.key_checks().get(key, ""))
        if not self.shown(ref):
            return Cell("")
        return Cell(*display(self.get_field(ref), self.answers.get(form, {}).get(key)))

    def data(self) -> dict:
        """What show-if rules see."""
        return {**self.answers, "_defects": [f"inspection.{k}" for k in self.defects],
                "_today": timezone.localdate().isoformat()}

    def values(self) -> dict:
        """What placeholders see: every value as text (worked out once)."""
        if self._values is None:
            self._values = self._all_values()
        return self._values

    def _all_values(self) -> dict:
        out: dict[str, dict] = {}
        for form, fields in self.fields.items():
            out[form] = {k: self.cell(f"{form}.{k}").text for k in fields}
        b, insp = self.booking, self.insp
        word = ((insp.scores or {}).get("overall") or {}).get("word") or ""
        from apps.forms.models import Form

        kind = Form.objects.filter(type="custom", inspection_type=b.inspection_type) \
            .values_list("name", flat=True).first() or b.inspection_type
        from django.conf import settings

        out["check"] = self.key_checks()
        out["sys"] = {
            "booking_id": b.booking_id, "inspection_type": kind,
            "expert": insp.expert.name or insp.expert.username,
            "inspected_on": timezone.localtime(insp.submitted_at).strftime("%d-%m-%Y")
            if insp.submitted_at else "",
            "submitted_at": timezone.localtime(insp.submitted_at).strftime("%d-%m-%Y %H:%M")
            if insp.submitted_at else "",
            "generated_at": timezone.localtime().strftime("%d-%m-%Y %H:%M"),
            "revision": str(self.revision), "issues": str(len(self.defects)),
            "overall": word.capitalize(), "verify_url": f"{settings.VERIFY_BASE_URL}/{self.token}",
            "car": _label("car_make_model", b.answers.get("car_make_model", "")),
        }
        checks = [(f, self.cell(f"inspection.{f.key}")) for f in self.form_fields()
                  if f.type in ("single_choice", "multi_choice")]
        answered = self.answers["inspection"]
        checks = [(f, c) for f, c in checks if c.text and c.tone]      # answered checks only
        unsure = [f.label for f, _ in checks  # a multi-choice answer is a list
                  if NOT_CHECKED & set(_as_list(answered.get(f.key)))]
        out["sys"].update(checks=str(len(checks)), not_checked=str(len(unsure)),
                          not_checked_list=", ".join(unsure))
        # the inspection's predefined checkpoints: every check, reading, detail, photo and video
        # asked on every car of this type. The same number for each such inspection: a photo or
        # remark asked only when a check finds a problem is not one, nor is what only Ops fill
        blank = evaluate_form(spec_from_version(self.version), {"booking": b.answers},
                              timezone.localdate().isoformat())
        points = [f for f in self.form_fields() if f.type not in NOT_POINTS
                  and blank.visible.get(f.key) and not _ops_only(f)]
        out["sys"]["points"] = str(len(points))
        from . import media_links

        out["sys"].update(media_links.values(self))      # photos_url, photo_count, videos_...
        return out

    def media(self, ref: str) -> list[str]:
        form, key = field_ref(ref)
        if not self.shown(ref):
            return []
        raw = self.answers.get(form, {}).get(key)
        return [str(x) for x in (raw if isinstance(raw, list) else [raw] if raw else [])]

    def section_fields(self, section_key: str) -> list[Field]:
        s = Section.objects.filter(version=self.version, key=section_key).first()
        return list(s.fields.order_by("order", "id")) if s else []

    def form_fields(self) -> list[Field]:
        """The inspection form's fields in the order the expert sees them."""
        order = {p: n for n, p in enumerate(Page.objects.filter(version=self.version)
                                            .order_by("order", "id").values_list("id", flat=True))}
        return sorted(self.fields["inspection"].values(),
                      key=lambda f: (order.get(f.section.page_id, 0), f.section.order,
                                     f.section_id, f.order, f.id))


# ---------------------------------------------------------------- parts

SEVERITY = ("minor", "major", "critical")


def flags(src: Source, ref: str, c: Cell) -> list[str]:
    """What style rules can match on one answer: problem, its colour, the worst severity
    chosen, 'not_checked', 'empty'."""
    out = [x for x in ("problem" if c.problem else "", c.tone or "",
                       "" if c.text else "empty") if x]
    f = src.get_field(ref)
    if f is not None and f.type in ("single_choice", "multi_choice"):
        form, key = field_ref(ref)
        raw = src.answers.get(form, {}).get(key)
        keys = raw if isinstance(raw, list) else [raw]
        opts = {o["key"]: o for o in f.config.get("options", [])}
        worst = [SEVERITY.index(opts[k]["severity"]) for k in keys
                 if opts.get(k, {}).get("severity") in SEVERITY]
        out += [SEVERITY[max(worst)]] if worst else []
        out += ["not_checked"] if NOT_CHECKED.intersection(map(str, keys)) else []
    return out


def _row(src: Source, ref: str, label: str | None, fallback: str | None) -> dict | None:
    form, key = field_ref(ref)
    if form == "check":                  # a Key Check row: its label from the form's list
        own = {kc["key"]: kc for kc in src.version.key_checks or [] if kc.get("in_report", True)}
        if key not in own:
            return None
        kc, c = own[key], src.cell(ref)
        if not c.text and fallback is None:
            return None
        # a Yes/No one keeps its colours: its "yes" means a problem was found
        tone = None if kc["type"] != "rule" else (
            "bad" if c.text == (kc.get("true_label") or "Yes")
            else "ok" if c.text == (kc.get("false_label") or "No") else None)
        return {"label": label or kc["label"], "text": c.text or fallback, "tone": tone,
                "problem": False, "empty": not c.text, "flags": []}
    f = src.get_field(ref)
    if f is None or not src.shown(ref):
        return None
    c = src.cell(ref)
    if not c.text and fallback is None:
        return None
    return {"label": label or f.label, "text": c.text or fallback, "tone": c.tone,
            "problem": c.problem, "empty": not c.text, "flags": flags(src, ref, c)}


def table_rows(src: Source, part: dict, data: dict) -> list[dict]:
    s = part["source"]
    if s["kind"] == "fields":
        rows = [_row(src, r["field"], r.get("label"), r.get("fallback")) for r in s["rows"]
                if truthy(r.get("show_if"), data)]
        return [r for r in rows if r]
    if s["kind"] == "section":
        skip = set(s.get("exclude", []))
        fields = [f for f in src.section_fields(s["section"].split(".", 1)[1])
                  if f.type not in NOT_ROWS and f.key not in skip]
        rows = [_row(src, f"inspection.{f.key}", None, s.get("fallback")) for f in fields]
        return [r for r in rows if r]
    out: list[dict] = []
    if s["kind"] == "defects":
        for f in src.form_fields():
            if f.key in src.defects:
                c = src.cell(f"inspection.{f.key}")
                out.append({"section": f.section.title, "label": f.label, "text": c.text,
                            "tone": c.tone, "problem": True, "empty": False,
                            "flags": flags(src, f"inspection.{f.key}", c)})
        return out
    values = src.values()                                            # grid
    for r in s["rows"]:
        if not truthy(r.get("show_if"), data):
            continue
        cells = []
        for cell in r["cells"]:
            if "field" in cell:
                c = src.cell(cell["field"])
                cells.append({"text": c.text or cell.get("fallback", ""), "tone": c.tone,
                              "problem": c.problem, "flags": flags(src, cell["field"], c)})
            else:
                cells.append({"text": placeholders.render(cell["text"], values, html=False),
                              "tone": None, "problem": False, "flags": []})
        if any(c["text"] for c in cells):
            out.append({"label": placeholders.render(r["label"], values, html=False),
                        "cells": cells})
    return out


def _shown(label: str) -> str:
    """A photo field's name as a caption: under a picture, "Image" / "Photo(s)" says nothing."""
    return re.sub(r"\s+(images?|photos?)$", "", label, flags=re.I) or label


def photo_items(src: Source, part: dict) -> list[dict]:
    s = part["source"]
    if s["kind"] == "fields":
        refs = list(s["fields"])
    elif s["kind"] == "section":
        refs = [f"inspection.{f.key}" for f in src.section_fields(s["section"].split(".", 1)[1])]
    else:                                                           # every issue photo
        refs = [f"inspection.{f.key}" for f in src.form_fields()]
    which = "issues" if s["kind"] == "issues" else part.get("which", "all")
    values = src.values()
    out = []
    for ref in refs:
        f = src.get_field(ref)
        # "Hide from customer" photos never print, even when placed by name (owner, 2026-11-27)
        if f is None or f.type != "photo" or f.key in src.customer_hidden:
            continue
        of = f.config.get("photo_of")
        check = src.cell(f"inspection.{of}") if of else None
        check_field = src.fields["inspection"].get(of) if of else None
        issue = f.config.get("issue_photo", False) or bool(check and check.problem)
        if which == "issues" and not issue:
            continue
        ids = src.media(ref)
        if which == "first":
            ids = ids[:1]
        kind = part.get("caption", "label")
        answer = check if kind == "check" and check_field and check and check.text else None
        caption = {
            "label": _shown(f.label),
            "check": check_field.label if answer and check_field else _shown(f.label),
            "custom": placeholders.render(part.get("caption_text", ""), values, html=False),
            "none": ""}[kind]
        out += [{"media": mid, "caption": caption, "answer": answer.text if answer else "",
                 "tone": answer.tone if answer else None} for mid in ids]
    return out


def _resolve(src: Source, parts: list[dict], data: dict, values: dict) -> list[dict]:
    out = []
    for part in parts:
        if not truthy(part.get("show_if"), data):
            continue
        item = {**part}
        t = part["type"]
        if t == "table":
            item["rows"] = table_rows(src, part, data)
            empty = not item["rows"]
        elif t == "photos":
            item["items"] = photo_items(src, part)
            empty = not item["items"]
        elif t == "button":                    # a link the customer taps in the PDF
            item["label_out"] = placeholders.render(part["label"], values, html=False)  # plain
            count = values["sys"].get(f"{part['link'][:-1]}_count", "")
            empty = count == "0"                           # nothing behind the link
        elif t in ("text", "html"):
            item["html_out"] = placeholders.render(part["html"], values)
            empty = not part["html"].strip()
        elif t == "snippet":                   # a shared part, filled in by shared.resolve
            item["parts"] = _resolve(src, part.get("parts", []), data, values)
            empty = not item["parts"]
        elif t == "columns":
            item["columns"] = [{**c, "parts": _resolve(src, c["parts"], data, values)}
                               for c in part["columns"]]
            empty = not any(c["parts"] for c in item["columns"])
        else:
            empty = False
        if empty and part.get("hide_when_empty", True):
            continue
        out.append(item)
    return out


def build(src: Source, definition: dict) -> list[dict]:
    """The pages that show, each with the parts that show and their resolved content."""
    data = src.data()
    values = src.values()
    pages = []
    for at, page in enumerate(definition.get("pages", [])):
        if truthy(page.get("show_if"), data):
            out = _resolve(src, page["parts"], data, values)
            if out:
                pages.append({**page, "parts": out, "at": at})     # at: its place in the template
    return pages
