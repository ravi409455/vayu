"""Everything a report shows, resolved from the stored data: labels come from the template, values
from the answers, colours from defect flags. Missing values print as blank rows, never errors."""
from datetime import date, datetime
from typing import Any

from apps.bookings.models import Booking, Inspection
from apps.bookings.services import booking_form_version
from apps.forms.models import PARTS, Field, MasterListItem
from apps.forms.rules import truthy

from .definition import field_ref


def latest_inspection(booking: Booking) -> Inspection | None:
    return booking.inspections.filter(status="submitted").order_by("-submitted_at").first()


def _label(list_key: str, item_key: str) -> str:
    return (MasterListItem.objects.filter(list__key=list_key, key=item_key)
            .values_list("label", flat=True).first() or str(item_key))


def _fmt_date(s: str) -> str:
    return date.fromisoformat(s).strftime("%d-%m-%Y")


def display(field: Field | None, value: Any, scores: dict) -> tuple[str, bool]:
    """(text, is_defect) for one value; blank when there is nothing to show."""
    if field is None or value is None:
        return "", False
    t, c = field.type, field.config
    if t in ("single_choice", "multi_choice"):
        options = {o["key"]: o for o in c.get("options", [])}
        chosen = value if isinstance(value, list) else [value]
        return (", ".join(options.get(k, {}).get("label", k) for k in chosen),
                any(options.get(k, {}).get("is_defect") for k in chosen))
    if t == "yes_no":
        return ("Yes" if value else "No"), False
    if t == "master_list":
        return _label(c.get("list", ""), value), False
    if t == "user_picker":
        from apps.accounts.models import User

        u = User.objects.filter(pk=value).first()
        return (u.name or u.username if u else ""), False
    if t == "number":
        return f"{value} {c['unit']}".strip() if c.get("unit") else str(value), False
    if t == "currency":
        return (f"₹{value:,.2f}" if value % 1 else f"₹{int(value):,}"), False
    if t == "date":
        return _fmt_date(value), False
    if t == "datetime":
        return datetime.fromisoformat(value).strftime("%d-%m-%Y %H:%M"), False
    if t == "gps":
        return f"{value['lat']:.5f}, {value['lng']:.5f}", False
    if t in ("photo", "video", "file"):
        return f"{len(value)} {t}{'' if len(value) == 1 else 's'}", False
    if t == "signature":
        return "Signed", False
    if t == "derived":
        return (c.get("true_label", "Yes") if value else c.get("false_label", "No")), False
    if t == "rating":
        return f"{value}/5", False
    return str(value), False


class Source:
    """Looks up (form, key) -> field and value across the booking, inspection, start and end
    forms, each as the version this inspection was started on."""

    def __init__(self, booking: Booking, insp: Inspection):
        self.scores = insp.scores or {}
        self.answers = {"booking": booking.answers,
                        **{p: (insp.answers.get(p) or {}) for p in PARTS}}
        self.fields: dict[str, dict[str, Field]] = {}
        versions = (("booking", booking_form_version()), *insp.pinned().items())
        for kind, version in versions:
            self.fields[kind] = ({f.key: f for f in Field.objects.filter(version=version)}
                                 if version else {})

    def value(self, ref: str) -> tuple[str, bool]:
        form, key = field_ref(ref)
        field = self.fields.get(form, {}).get(key)
        if field is not None and field.type == "derived":
            raw = self.scores.get("derived", {}).get(key)
        elif field is not None and field.type == "rating":
            raw = self.scores.get("fields", {}).get(key)
        else:
            raw = self.answers.get(form, {}).get(key)
        return display(field, raw, self.scores)

    def media(self, ref: str, index: int = 0) -> str | None:
        form, key = field_ref(ref)
        raw = self.answers.get(form, {}).get(key)
        ids = raw if isinstance(raw, list) else ([raw] if raw else [])
        return ids[index] if 0 <= index < len(ids) else None

    def data(self) -> dict:
        return {**self.answers, "_defects": self.scores.get("defects", []),
                "_today": date.today().isoformat()}


def build(booking: Booking, insp: Inspection, definition: dict) -> list[dict]:
    """The blocks of the report with every value resolved, hidden blocks dropped."""
    src = Source(booking, insp)
    data = src.data()
    out: list[dict] = []
    for blk in definition.get("blocks", []):
        if not truthy(blk.get("show_if"), data):
            continue
        t = blk["type"]
        rows = [{"label": r["label"], "text": (v := src.value(r["field"]))[0], "defect": v[1]}
                for r in blk.get("rows", [])]
        item = {"type": t, "font_size": blk.get("font_size", "medium"),
                "title": blk.get("title", ""), "text": blk.get("text", ""), "rows": rows,
                "height": blk.get("height", 10)}
        if t == "cover":
            item["photo"] = src.media(blk["photo"]) if blk.get("photo") else None
        if t == "photos":
            item["columns"] = blk.get("columns", 2)
            item["items"] = [{"media": src.media(i["field"], i.get("index", 0)),
                              "caption": i.get("caption", "")} for i in blk.get("items", [])]
        if t == "ratings":
            r = src.scores.get("ratings", {})
            labels = {c["key"]: c["label"] for c in
                      (insp.form_version.rating_config or {}).get("categories", [])}
            item["rows"] = [{"label": labels.get(k, k), "text": f"{v['value']}/5", "defect": False}
                            for k, v in r.items()]
            word = src.scores.get("overall", {}).get("word")
            item["overall"] = word.capitalize() if word else ""
        out.append(item)
    return out
