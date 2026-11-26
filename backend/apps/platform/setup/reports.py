"""The PDF report of each inspection form, in the approved PDI report's design (cover, ratings,
issues, Key Checks, one page per section, car pictures, verify page, disclaimer), built from that
form's own sections. The look (theme) and the disclaimer are shared items, edited once for all."""
import io
import json
from pathlib import Path
from typing import Any

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
# the Ops-only pages (common.py): never a page of checks, each prints in its own place
OPS_COMMENTS, OPS_CHECKS, OPS_DETAILS = "Expert Comments", "Key Checks", "Additional Details"
SERVICE = "Service History Details"
DELAY = "Inspection Delay"        # a late start and its payment: ours, never the customer's
VARIANT = "Car Variant"
# what an empty service-history answer prints (Clappia's starting values)
SERVICE_EMPTY = {"indication_of_odometer_rollback": "Not able to check", "engine_work_done": "No",
                 "transmission_work_done": "No", "service_history_analysis": None}
# the cover's details: short names, so each row keeps to one line (the form's labels stay)
SHORT = {"Car KM Current Reading": "Odometer", "Number of Car Keys Available": "Keys",
         "Engine Capacity (in CC)": "Engine Capacity", "Car Registered State": "Reg. State",
         "Car Registered City": "Reg. City", "Car Registration Number": "Registration No.",
         "Car Registration Year (Model)": "Model Year",
         "Car Colour": "Colour", "Transmission Type": "Transmission",
         "Chassis Number": "Chassis No.", "Engine Number": "Engine No."}
ALSO_PICTURED = ("gear_shifting_panel",)       # photos from other sections on Car pictures
SHARE = "_share"      # on a page while it is built: (shared part key, name, from part[, to part])


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


def _cols(*columns: list, widths: tuple = (), align: str = "top") -> dict:
    return {"type": "columns", "gap": 6, **({"align": align} if align != "top" else {}),
            "columns": [{"parts": c, **({"width": widths[k]} if widths else {})}
                        for k, c in enumerate(columns)]}


def _grid(columns: list, cells: list, **look) -> dict:
    return {"type": "table", "look": {"header": True, "emphasis": True, "stripes": False, **look},
            "source": {"kind": "grid", "columns": columns,
                       "rows": [{"label": "", "cells": cells}]}}


def _details(rows: list[tuple]) -> dict:
    """The cover's label / value list. A row is (label, a field or a line of text, shown when);
    one whose answer is empty is left out."""
    return {"type": "table", "look": {"kv": True, "stripes": False, "header": False},
            "source": {"kind": "grid", "columns": [{"label": "Value"}], "rows": [
                {"label": label, "cells": [cell], **({"show_if": when} if when else {})}
                for label, cell, when in rows]}}


def _documents(docs, priced: bool) -> list[dict]:
    """The cover's documents; on a Used Car, Ops' price estimate beside them (as on Clappia)."""
    if docs is None:
        return []
    if not priced:
        return [_heading("Documents"), _sec(docs.key, per_row=2, header=False)]
    shown = _filled("price_estimate")
    price = ("font-family: var(--head); font-weight: 700; text-align: center; "
             "color: var(--brand); font-size: 2.1em; line-height: 1.2; margin-top: 3mm")
    return [{"type": "spacer", "height": 6},              # room under the rating tables
            _cols([_heading("Documents"), _sec(docs.key, header=False)], [
                {"type": "html", "show_if": shown, "html": "Estimated Price",
                 "css": "font-family: var(--head); font-weight: 700; font-size: 1.7em; "
                        "text-align: center; margin-bottom: 2mm"},
                {"type": "text", "align": "center", "size": "small", "show_if": shown,
                 "html": '<p class="tone-muted">This estimate reflects the overall condition of '
                         "the car, considering factors such as the quality of the exterior, "
                         "interior, and mechanical components</p>"},
                {"type": "html", "show_if": shown, "html": "{{ inspection.price_estimate }}",
                 "css": price}], widths=(50, 50))]


def _service_history(section) -> list[dict]:
    """Used Car: the service centre's record on a page of its own (after the pictures, before the
    verify page). An answer Ops left empty prints Clappia's starting value."""
    if section is None:
        return []
    rows = []
    for f in section.fields.order_by("order"):
        empty = SERVICE_EMPTY.get(f.key, "NA")
        rows.append({"field": f"inspection.{f.key}", **({"fallback": empty} if empty else {})})
    return [{"title": "Service history", "style": "normal", "parts": [
        _heading("Service history", "from the authorised service centre's records"),
        {"type": "table", "look": {"header": False},
         "source": {"kind": "fields", "rows": rows}}]}]


def _filled(key: str) -> dict:
    return {"!!": [{"var": f"inspection.{key}"}]}


def _own_checks(sec) -> list[dict]:
    """The key checks Ops named themselves: one row per pair whose label is filled, in a table
    of its own that (with its heading) is left out when Ops added none."""
    if sec is None:
        return []
    keys = [f.key for f in sec.fields.order_by("order")]
    pairs = [(k, k[:-len("label")] + "value") for k in keys if k.endswith("_label")]
    pairs = [(a, b) for a, b in pairs if b in keys]
    if not pairs:
        return []
    any_named = {"or": [_filled(a) for a, _ in pairs]}
    return [{**_heading("Additional key checks"), "show_if": any_named},
            {"type": "table", "look": {"header": False},
             "source": {"kind": "grid", "columns": [{"label": "Check"}, {"label": "Result"}],
                        "rows": [{"label": "", "show_if": _filled(a),
                                  "cells": [{"field": f"inspection.{a}"},
                                            {"field": f"inspection.{b}"}]} for a, b in pairs]}}]


def _comments(ops_section) -> list[dict]:
    """"Expert comments": what Ops wrote on their page, and nothing when they wrote nothing. The
    expert's own summary ("Any Issues found in the car?") is never printed, as in Clappia: only
    its photos are (owner, 2026-11-26)."""
    if ops_section is None:
        return []
    ops = ops_section.fields.order_by("order").first().key
    box = {"padding": 3, "background": "muted", "border": "left", "border_color": "brand",
           "border_width": 1}
    return [{**_heading("Expert comments"), "show_if": _filled(ops)},
            {"type": "text", "html": f"<p>{{{{ inspection.{ops} }}}}</p>", "box": box,
             "show_if": _filled(ops)}]


def _section_page(s, page, kids: list, shared: bool) -> dict:
    """One section's report page: its checks and photos, then (same heading, same table style)
    those of the sections split off from it."""
    # a section on a test-drive page says so ("Axle  during test drive")
    sub = "" if page.title == s.title or page.title.lower() in s.title.lower() else (
        "during test drive" if page.title == "Test drive" else page.title.lower())
    two: dict[str, Any] = {"per_row": 2} if s.title.lower().startswith(TWO_PER_ROW) else {}
    tables = [_sec(c.key, header=False, **two) for c in kids]      # the checks stay together
    part = {"title": s.title, "style": "normal",
            "parts": [_heading(s.title, sub), _sec(s.key, **two), *tables, _photos(s.key),
                      *[_photos(c.key) for c in kids]]}
    if s.show_if:
        part["show_if"] = s.show_if
    if shared:                      # the heading stays the page's (Used Car adds the phase)
        part[SHARE] = (f"section_{s.key}", f"{s.title}: checks and photos", 1)
    return part


# small sections that share a report page (review, 2026-11-27), in the form's own order
TOGETHER = [{"Battery and Charging", "OBD Scan"}, {"Transmission and Clutch Pedal", "Axle"}]


def _together(pages: list[dict]) -> list[dict]:
    """The section pages, with each pair of small sections on one page (each keeps its heading)."""
    out: list[dict] = []
    for page in pages:
        first = next((p for p in out for pair in TOGETHER
                      if page["title"] in pair and p["title"] in pair - {page["title"]}
                      and "show_if" not in p and "show_if" not in page), None)
        if first is None:
            out.append(page)
            continue
        first["parts"] = [*first["parts"], *page["parts"]]
        first["title"] = f"{first['title']} and {page['title']}"
        first.pop(SHARE, None)              # two sections on it: no longer one shared part
    return out


def _family(form_key: str) -> tuple[dict[str, str], set[str], dict]:
    """(this form's split-off section → the shared one it prints with, the sections something is
    split off from in any form, the library sections). A section page is one shared part when
    all three forms print the very same thing: a library section every form has, with nothing
    split off from it anywhere (setup/common.py)."""
    from . import forms as setup_forms

    def parents(key: str) -> dict[str, str]:
        return {x["title"]: x["parent"] for pg in setup_forms.inspection(key)[0]["pages"]
                for x in pg["sections"] if x.get("parent")}

    everywhere = {p for k, *_ in setup_forms.INSPECTIONS for p in parents(k).values()}
    return parents(form_key), everywhere, setup_forms.library()["sections"]


def definition(version, form_key: str, logo: str, watermark: str) -> dict:
    """The report of one published inspection version."""
    from . import pdi_report

    code = TITLES[form_key]
    sections = [(s, s.page) for s in Section.objects.filter(version=version)
                .select_related("page").order_by("page__order", "order", "id")]
    by_title = {s.title: s for s, _ in sections}
    cats = (version.rating_config or {}).get("categories", [])

    parent, split_somewhere, lib = _family(form_key)

    def kids(title: str) -> list:
        return [c for c, _ in sections if parent.get(c.title) == title]

    def same_everywhere(sec) -> bool:
        item = sec.library_item
        return (item is not None and len(lib.get(item.key, {}).get("forms", [])) == 3
                and sec.title not in split_somewhere)

    car = by_title.get("Car Details")
    kv_rows: list[tuple[str, dict[str, str], dict | None]] = [
        ("Booking ID", {"field": "booking.booking_id"}, None)]
    if car is not None:
        # chassis first; not "Car Company" (the Car row names it) nor the variant (it is part of
        # the Car row: "Honda Amaze VXI")
        details = sorted((f for sec in (car, *kids(car.title)) for f in sec.fields.order_by("order")
                          if f.type not in ("photo", "video") and "company" not in f.label.lower()),
                         key=lambda f: f.key != "chassis_no")
        variant = next((f.key for f in details if f.label == VARIANT), None)
        kv_rows.append(("Car", {"text": "{{ sys.car }}" + (
            f" {{{{ inspection.{variant} }}}}" if variant else "")}, None))
        rows = [(SHORT.get(f.label, f.label), {"field": f"inspection.{f.key}"}, _filled(f.key))
                for f in details if f.label != VARIANT][:10]
        if by_title.get(OPS_DETAILS) is not None:      # what Ops found on the plate (PDI, EV)
            rows.insert(1, ("Mfg. Date", {"field": "inspection.manufacturing_date"},
                            _filled("manufacturing_date")))
        kv_rows += rows
    else:
        kv_rows.append(("Car", {"text": "{{ sys.car }}"}, None))
    pics = by_title.get(PICTURES)
    cover_photo = next((f.key for f in pics.fields.order_by("order") if f.type == "photo"),
                       None) if pics else None

    cover = [_cols([{"type": "photos", "per_row": 1, "shape": "4:3", "caption": "none",
                     "source": {"kind": "fields", "fields": [f"inspection.{cover_photo}"]}}]
                   if cover_photo else [],
                   [_details(kv_rows)], widths=(52, 48),
                   align="middle"),          # the photo sits centred beside the details
             _heading("Overall rating"),
             _grid([{"label": c["label"]} for c in cats] + [{"label": "Expert rating",
                                                             "width": 22}],
                   [{"field": f"inspection.rating_{c['key']}"} for c in cats]
                   + [{"text": "{{ sys.overall }}"}]),
             # what the customer sees at a glance: the problems, and how much was looked at
             # (every check, reading, photo and video the expert recorded)
             _grid([{"label": "Issues found"}, {"label": "Checkpoints inspected"}],
                   [{"text": "{{ sys.issues }}"}, {"text": "{{ sys.points }}"}])]
    docs = by_title.get("Car Documents")
    cover += _documents(docs, priced=form_key == "used_car" and OPS_DETAILS in by_title)

    summary = [_heading("Issues found", "from all sections"),
               # every row alike: the result's own colour says how bad (review, 2026-11-27)
               {"type": "table", "source": {"kind": "defects"}},
               {"type": "photos", "per_row": 3, "caption": "check", "source": {"kind": "issues"}}]
    # the issues have a page to themselves; Key Checks, Ops' own and the comment share the next
    checks = [kc for kc in version.key_checks or [] if kc.get("in_report", True)]
    review: list[dict] = []
    if checks:
        review += [_heading("Key checks"), {"type": "table", "source": {
            "kind": "fields", "rows": [{"field": f"check.{kc['key']}"} for kc in checks]}}]
    review += _own_checks(by_title.get(OPS_CHECKS))
    review += _comments(by_title.get(OPS_COMMENTS))

    pages = [{"title": "Cover", "style": "cover", "parts": cover},     # Key checks come first
             *([{"title": "Key checks", "style": "normal", "parts": review}] if review else []),
             {"title": "Issues found", "style": "normal", "parts": summary},
             {"title": "Detailed report", "style": "full", "parts": [
                 {"type": "spacer", "height": 70},
                 {"type": "text", "align": "center", "size": "small",
                  "html": '<p class="tone-brand"><strong>{{ sys.booking_id }} · {{ sys.car }}'
                          "</strong></p>"},
                 {"type": "text", "size": "title", "align": "center",
                  "html": "<p>Detailed Report</p>"},
                 {"type": "spacer", "height": 10},
                 _cols([], [{"type": "contents", "columns": 2}], [], widths=(15, 70, 15))]}]
    pages += _together([_section_page(sec, page, kids(sec.title), same_everywhere(sec))
                        for sec, page in sections
                        if sec.title not in (*COVER, PICTURES, FINAL, RATINGS, OPS_COMMENTS,
                                             OPS_CHECKS, OPS_DETAILS, SERVICE, DELAY, *parent)])
    if pics is not None:
        # the overview photos are one shared part; a form's own extra pictures follow them
        more = [f"inspection.{f.key}" for sec, _ in sections for f in sec.fields.order_by("order")
                if f.key in ALSO_PICTURED]
        pages.append({"title": "Car pictures", "style": "normal", SHARE: (
            "car_pictures", "Car pictures", 0, 2), "parts": [
            _heading("Car pictures"),
            {"type": "photos", "per_row": 2,
             "source": {"kind": "section", "section": f"inspection.{pics.key}"}},
            *([{"type": "photos", "per_row": 2,
                "source": {"kind": "fields", "fields": more}}] if more else [])]})

    # the approved PDI report gives the look, the verify page and the disclaimer
    base = pdi_report.pdf_definition(logo, watermark, "")
    verify = next(p for p in base["pages"] if p["title"] == "Verify this report")
    for k, part in enumerate(verify["parts"]):           # the link is a button, as the downloads
        if part["type"] == "text" and "open the link" in part.get("html", ""):
            part["html"] = part["html"].replace("open the link", "tap the button below it")
        if part["type"] == "verify":
            part["show_url"] = False                      # the button carries the link
            verify["parts"].insert(k + 1, {"type": "button", "link": "verify",
                                           "label": "Verify this report"})
            break
    pages += _service_history(by_title.get(SERVICE))
    verify[SHARE] = ("verify_report", "Verify this report", 0)
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
    for pg in definition["pages"]:         # pages identical in all three reports: one shared part
        if SHARE in pg:
            key, name, start, *stop = pg.pop(SHARE)
            end = stop[0] if stop else len(pg["parts"])
            item = save("snippet", key, name, {"parts": pg["parts"][start:end]})
            pg["parts"] = pg["parts"][:start] + [
                {"type": "snippet", "ref": {"key": key, "revision": item.revision}}
            ] + pg["parts"][end:]
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


