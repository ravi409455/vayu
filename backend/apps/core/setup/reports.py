"""The PDF report of each inspection form, in the approved PDI report's design (cover, ratings,
issues, Key Checks, one page per section, car pictures, verify page, disclaimer), built from that
form's own sections. The look (theme) and the disclaimer are shared items, edited once for all."""
import io
import json
from pathlib import Path

from apps.forms.models import Form, FormAsset, Section, VersionStatus

ASSETS = Path(__file__).resolve().parents[1] / "seed_assets"
TITLES = {"pdi": "PDI", "used_car": "PPI", "ev": "EV"}       # the PDF's file name ending
# sections the report shows in their own places, not as a page of checks
COVER = ("Car Details", "Car Documents")
PICTURES = "Car Images From All Directions"
FINAL = "Final Car Result"
RATINGS = "Ratings"
# long sections print two checks a row (four columns)
TWO_PER_ROW = ("exterior", "body frame", "engine", "electrical", "tyres")


def brand(admin) -> tuple[str, str]:
    """The Car C.I.D. logo and watermark as uploaded pictures (made once, then found by name)."""
    from PIL import Image

    from apps.forms import assets

    out = []
    for name, edge, label in (("carcid-logo.webp", 400, "Car C.I.D. logo"),
                              ("carcid-watermark.webp", 900, "Car C.I.D. watermark")):
        found = FormAsset.objects.filter(name=label).first()
        if found is None:
            img = Image.open(ASSETS / name).convert("RGBA")
            img.thumbnail((edge, edge))
            buf = io.BytesIO()
            img.save(buf, "PNG", optimize=True)
            found = assets.create_asset(admin, buf.getvalue(), label)
        out.append(str(found.id))
    return out[0], out[1]


def _sec(key: str, title: str = "", header: bool = True, **kw) -> dict:
    return {"type": "table", "title": title, "look": {"header": header},
            "source": {"kind": "section", "section": f"inspection.{key}"},
            "style_rules": [{"when": "not_checked", "value": "muted"}], **kw}


def _photos(key: str) -> dict:
    """Every photo the section has: the always-taken ones (tyres, readings, underbody) and the
    problem ones (asked only when a check fails)."""
    return {"type": "photos", "per_row": 3, "caption": "check",
            "source": {"kind": "section", "section": f"inspection.{key}"}}


def _heading(text: str, sub: str = "") -> dict:
    small = f' <span class="small">{sub}</span>' if sub else ""
    return {"type": "text", "html": f"<h2>{text}{small}</h2>", "box": {"space_below": 0.5}}


def _cols(*columns: list, widths: tuple = ()) -> dict:
    return {"type": "columns", "gap": 6, "columns": [
        {"parts": c, **({"width": widths[k]} if widths else {})} for k, c in enumerate(columns)]}


def _grid(columns: list, cells: list, **look) -> dict:
    return {"type": "table", "look": {"header": True, "emphasis": True, "stripes": False, **look},
            "source": {"kind": "grid", "columns": columns,
                       "rows": [{"label": "", "cells": cells}]}}


def definition(version, form_key: str, logo: str, watermark: str) -> dict:
    """The report of one published inspection version."""
    from apps.core import demo_pdi

    code = TITLES[form_key]
    sections = [(s, s.page) for s in Section.objects.filter(version=version)
                .select_related("page").order_by("page__order", "order", "id")]
    by_title = {s.title: s for s, _ in sections}
    cats = (version.rating_config or {}).get("categories", [])

    car = by_title.get("Car Details")
    kv_rows = [{"field": "booking.booking_id", "label": "Booking ID"},
               {"field": "booking.car_make_model", "label": "Car"}]
    if car is not None:
        # 12 rows, as approved: chassis first, not "Car Company" (the Car row names it)
        details = sorted((f for f in car.fields.order_by("order") if f.type not in (
            "photo", "video") and "company" not in f.label.lower()),
            key=lambda f: f.key != "chassis_no")
        kv_rows += [{"field": f"inspection.{f.key}"} for f in details][:10]
    pics = by_title.get(PICTURES)
    cover_photo = next((f.key for f in pics.fields.order_by("order") if f.type == "photo"),
                       None) if pics else None
    final = by_title.get(FINAL)
    comments = next((f.key for f in final.fields.all() if f.type == "long_text"), None) \
        if final else None

    cover = [_cols([{"type": "photos", "per_row": 1, "shape": "4:3", "caption": "none",
                     "source": {"kind": "fields", "fields": [f"inspection.{cover_photo}"]}}]
                   if cover_photo else [],
                   [{"type": "table", "look": {"kv": True, "stripes": False, "label_width": 42},
                     "source": {"kind": "fields", "rows": kv_rows}}], widths=(52, 48)),
             _heading("Overall rating"),
             _grid([{"label": c["label"]} for c in cats] + [{"label": "Expert rating",
                                                             "width": 22}],
                   [{"field": f"inspection.rating_{c['key']}"} for c in cats]
                   + [{"text": "{{ sys.overall }}"}]),
             _grid([{"label": "Issues found"}, {"label": "Not able to check"},
                    {"label": "Checks done"}],
                   [{"text": "{{ sys.issues }}"}, {"text": "{{ sys.not_checked }}"},
                    {"text": "{{ sys.checks }}"}])]
    docs = by_title.get("Car Documents")
    if docs is not None:
        cover += [_heading("Documents"), _sec(docs.key, per_row=2, header=False)]

    summary = [_heading("Issues found", "from all sections"),
               {"type": "table", "source": {"kind": "defects"},
                "style_rules": [{"when": "critical", "bold": True, "background": "bad"}]},
               {"type": "photos", "per_row": 3, "caption": "check", "source": {"kind": "issues"}},
               {"type": "text", "html": '<p><strong class="tone-warn">Not able to check:</strong> '
                                        "{{ sys.not_checked_list }}</p>"}]
    checks = [kc for kc in version.key_checks or [] if kc.get("in_report", True)]
    if checks:
        summary += [_heading("Key checks"), {"type": "table", "source": {
            "kind": "fields", "rows": [{"field": f"check.{kc['key']}"} for kc in checks]}}]
    if comments:
        summary += [_heading("Expert comments"),
                    {"type": "text", "html": f"<p>{{{{ inspection.{comments} }}}}</p>",
                     "box": {"padding": 3, "background": "muted", "border": "left",
                             "border_color": "brand", "border_width": 1}}]

    pages = [{"title": "Cover", "style": "cover", "parts": cover},
             {"title": "Summary", "style": "normal", "parts": summary},
             {"title": "Detailed report", "style": "full", "parts": [
                 {"type": "spacer", "height": 70},
                 {"type": "text", "align": "center", "size": "small",
                  "html": '<p class="tone-brand"><strong>{{ sys.booking_id }} · {{ sys.car }}'
                          "</strong></p>"},
                 {"type": "text", "size": "title", "align": "center",
                  "html": "<p>Detailed Report</p>"},
                 {"type": "spacer", "height": 10},
                 _cols([], [{"type": "contents", "columns": 2}], [], widths=(15, 70, 15))]}]
    for s, page in sections:
        if s.title in (*COVER, PICTURES, FINAL, RATINGS):
            continue
        # a section on a test-drive page says so ("Axle  during test drive")
        sub = "" if page.title == s.title or page.title.lower() in s.title.lower() else (
            "during test drive" if page.title == "Test drive" else page.title.lower())
        table = (_sec(s.key, per_row=2) if s.title.lower().startswith(TWO_PER_ROW)
                 else _sec(s.key))
        part = {"title": s.title, "style": "normal",
                "parts": [_heading(s.title, sub), table,
                          _photos(s.key)]}
        if s.show_if:
            part["show_if"] = s.show_if
        pages.append(part)
    if pics is not None:
        pages.append({"title": "Car pictures", "style": "normal", "parts": [
            _heading("Car pictures"),
            {"type": "photos", "per_row": 2,
             "source": {"kind": "section", "section": f"inspection.{pics.key}"}}]})

    # the approved PDI report gives the look, the verify page and the disclaimer
    base = demo_pdi.pdf_definition(logo, watermark, "")
    verify = next(p for p in base["pages"] if p["title"] == "Verify this report")
    for k, part in enumerate(verify["parts"]):           # the link is a button, as the downloads
        if part["type"] == "text" and "open the link" in part.get("html", ""):
            part["html"] = part["html"].replace("open the link", "tap the button below it")
        if part["type"] == "verify":
            part["show_url"] = False                      # the button carries the link
            verify["parts"].insert(k + 1, {"type": "button", "link": "verify",
                                           "label": "Verify this report"})
            break
    pages += [verify, {"title": "Disclaimer", "style": "normal", "parts": []}]
    base["pages"] = pages
    base["filename"] = "{{ sys.booking_id }}" + code + ".pdf"
    # the header is part of the shared look, so it names the form by placeholder (one look for all)
    base["bands"]["normal"]["header"]["right"][0] = {
        "text": "<strong>{{ sys.inspection_type }} REPORT</strong>"}
    base["bands"]["cover"]["header"]["right"][0] = {
        "text": "<strong>{{ sys.inspection_type }}</strong>"}
    return base


def _shared(admin, definition: dict, force: bool = False) -> dict:
    """The look and the disclaimer as shared items (one edit changes every report). Made once;
    after that they are the Admin's, saved again only when [force]d (H-11)."""
    from apps.reports import shared
    from apps.reports.models import SharedItem

    def save(kind, key, name, content):
        found = SharedItem.objects.filter(kind=kind, key=key).first()
        return found if found is not None and not force else shared.save(
            admin, kind, key, name, content)[0]

    theme = {k: definition.pop(k) for k in shared.THEME_KEYS if k in definition}
    item = save("theme", "carcid", "Car C.I.D.", theme)
    definition["theme_ref"] = {"key": "carcid", "revision": item.revision}
    text = (ASSETS / "pdi-disclaimer.html").read_text()
    item = save("snippet", "disclaimer", "Report disclaimer",
                {"parts": [{"type": "text", "columns": 2, "size": "fine", "html": text}]})
    page = next(p for p in definition["pages"] if p["title"] == "Disclaimer")
    page["parts"] = [{"type": "snippet", "ref": {"key": "disclaimer",
                                                 "revision": item.revision}}]
    return definition


def apply(admin, form_key: str, force: bool = False) -> str:
    """The form's report template, made when it has none ("published v<n>"); a template already
    live is the Admin's and is "kept" unless [force]d, never over a draft they have open."""
    from apps.reports import service as reports
    from apps.reports.models import PdfTemplate

    form = Form.objects.get(key=form_key)
    version = form.versions.filter(status=VersionStatus.PUBLISHED).order_by("-number").first()
    logo, mark = brand(admin)
    from apps.reports.service import validate_definition

    from .build import SetupRefused

    template = PdfTemplate.objects.filter(form=form).first() or reports.create_template(admin,
                                                                                         form)
    live = template.versions.filter(status="published").order_by("-number").first()
    if live is not None and not force:
        return "kept"
    want = validate_definition(_shared(admin, definition(version, form_key, logo, mark), force))
    if live is not None and json.dumps(live.definition, sort_keys=True) == json.dumps(
            want, sort_keys=True):
        return "unchanged"
    draft = template.versions.filter(status="draft").first()
    if live is not None and draft is not None:
        raise SetupRefused(f"The {form.name} report has a draft open in the designer: publish or "
                           "discard it first. Nothing was changed.")
    draft = draft or reports.create_draft(admin, template)
    saved = reports.save_definition(admin, draft, want, draft.row_version)
    v = reports.publish(admin, saved, saved.row_version)
    return f"published v{v.number}"


def ratings_section(categories: list[dict]) -> dict:
    """The Ops-only page of rating fields the report prints (filled by scoring, not the expert)."""
    return {"title": RATINGS, "sections": [{"title": RATINGS, "fields": [
        {"key": f"rating_{c['key']}", "label": f"{c['label']} rating", "type": "rating",
         "config": {"category": c["key"]}, "required": False} for c in categories]}]}


