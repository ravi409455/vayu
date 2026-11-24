"""HTML and PDF for a report. WeasyPrint turns the HTML into pages: running header and footer
bands per page style, repeated table headers, page numbers. Every image is embedded by us as a
data URI, and the renderer loads nothing else (no files, no network)."""
import base64
import html
import io
import os
import re
import sys
from functools import cache
from pathlib import Path
from typing import Any

import qrcode
from markupsafe import Markup

from apps.forms.models import FormAsset
from apps.media import storage
from apps.media.models import MediaAsset

from . import placeholders

PAPER = {"A4": (210, 297), "Letter": (216, 279)}
MARGINS = {"top": 26, "right": 12, "bottom": 16, "left": 12}
COLORS = {"brand": "#a62830", "text": "#1b1f27", "ok": "#15703f", "warn": "#b25e09",
          "bad": "#b3261e", "muted": "#8a93a3"}
PRINT_EDGE = 1000            # print photos: about 1000 px is plenty at 2-3 per row on A4
PADS = {"compact": 0.6, "normal": 1.2, "roomy": 2.0}
RATIO = {"4:3": 0.75, "16:9": 0.5625, "1:1": 1.0}
FONTS_DIR = Path(__file__).parent / "fonts"
FONT_FILES = {"Inter": (400, 600, 700), "Barlow Semi Condensed": (500, 600, 700)}
STACK = {"Inter": '"Inter", Helvetica, Arial, sans-serif',
         "Barlow Semi Condensed": '"Barlow Semi Condensed", "Inter", Helvetica, sans-serif',
         "Helvetica": "Helvetica, Arial, sans-serif"}
SCORE = re.compile(r"^(\d)/5$")


def e(s: Any) -> str:
    return html.escape(str(s))


# ---------------------------------------------------------------- images

def _jpeg_uri(data: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(data).decode()


def print_image(media_id: str, edge: int = PRINT_EDGE) -> str | None:
    """A verified photo as a data URI, shrunk once for print and kept (originals untouched).
    edge <= 480 uses the preview made at upload (the designer's live preview)."""
    from PIL import Image, ImageOps

    asset = MediaAsset.objects.filter(pk=media_id, status="verified").first()
    if asset is None:
        return None
    if edge <= 480 and asset.preview_key:
        return _jpeg_uri(storage.read(asset.preview_key))
    key = f"print/{asset.id}-{edge}.jpg"
    if storage.exists(key):
        return _jpeg_uri(storage.read(key))
    try:
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(storage.read(asset.key))))
    except (OSError, ValueError, Image.DecompressionBombError):
        return None
    image.thumbnail((edge, edge))
    buf = io.BytesIO()
    image.convert("RGB").save(buf, "JPEG", quality=80)
    storage.put(key, buf.getvalue(), "image/jpeg")
    return _jpeg_uri(buf.getvalue())


def asset_uri(asset_id: str, opacity: float = 1.0) -> str | None:
    """An uploaded picture (logo, watermark) as a data URI, faded when opacity < 1."""
    from PIL import Image

    asset = FormAsset.objects.filter(pk=asset_id).first()
    if asset is None:
        return None
    data = storage.read(asset.key)
    if opacity >= 1:
        return f"data:{asset.content_type};base64," + base64.b64encode(data).decode()
    image = Image.open(io.BytesIO(data)).convert("RGBA")
    alpha = image.getchannel("A").point(lambda a: int(a * opacity))
    image.putalpha(alpha)
    buf = io.BytesIO()
    image.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def qr_uri(text: str) -> str:
    buf = io.BytesIO()
    qrcode.make(text, box_size=6, border=1).save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


# ---------------------------------------------------------------- parts

def _box(part: dict) -> str:
    b = part.get("box", {})
    css = [f"margin-top:{b.get('space_above', 0)}mm", f"margin-bottom:{b.get('space_below', 3)}mm"]
    if b.get("padding"):
        css.append(f"padding:{b['padding']}mm")
    border = b.get("border", "none")
    if border != "none":
        line = f"{b.get('border_width', 0.4)}mm solid var(--{b.get('border_color', 'muted')})"
        css.append(f"border:{line}" if border == "all" else f"border-{border}:{line}")
    if b.get("background", "none") != "none":
        css.append(f"background:var(--{b['background']}-tint)")
    if b.get("round"):
        css.append("border-radius:2mm")
    if part.get("keep_together"):
        css.append("break-inside:avoid")
    if part.get("new_page"):
        css.append("break-before:page")
    return ";".join(css)


def _value(r: dict, emphasis: bool = False) -> str:
    if emphasis and (m := SCORE.match(r["text"])):                 # 4/5 as a big 4 and dots
        n = int(m[1])
        dots = "".join(f'<i class="{"" if k < n else "off"}"></i>' for k in range(5))
        return f'<span class="big">{n}<small>/5</small></span><span class="dots">{dots}</span>'
    if r.get("problem"):
        return f'<span class="chip tone-{r["tone"] or "bad"}">{e(r["text"])}</span>'
    classes = " ".join(c for c in ("big" if emphasis else "",
                                   f"tone-{r['tone']}" if r.get("tone") else "") if c)
    return f'<span class="{classes}">{e(r["text"])}</span>' if classes \
        else f"<span>{e(r['text'])}</span>"


def _styled(r: dict, rules: list[dict]) -> tuple[dict, str, str, str]:
    """A row with the style rules that match it: (row, label class, bold class, background
    style). Later rules win, e.g. 'problem: red answer' then 'critical: red background'."""
    label, bold, bg = "", False, ""
    for rule in rules:
        if rule["when"] not in r.get("flags", ()):
            continue
        r = {**r, "tone": rule.get("value", r["tone"])}
        label = rule.get("label", label)
        bold = bold or rule.get("bold", False)
        bg = rule.get("background", bg)
    return (r, f" tone-{label}" if label else "", " rb" if bold else "",
            f' style="background:var(--{bg}-tint)"' if bg and bg != "none" else "")


def _td(rb: str, st: str) -> str:
    return (f' class="{rb[1:]}"' if rb else "") + st


def _table(part: dict) -> str:
    look = part.get("look", {})
    rules = part.get("style_rules", [])
    kind = part["source"]["kind"]
    cls = (f"t lines-{look.get('lines', 'rows')}" + (" stripes" if look.get("stripes", True) else "")
           + (" emphasis" if look.get("emphasis") else "") + (" kv" if look.get("kv") else ""))
    pad = PADS[look.get("height", "normal")]
    style = f' style="--pad:{pad}mm"'
    rows = part["rows"]
    big = bool(look.get("emphasis"))
    if kind == "grid":
        cols = part["source"]["columns"]
        labels = any(r["label"] for r in rows)
        widths = [f' style="width:{c["width"]}%"' if c.get("width") else "" for c in cols]
        head = ("<th></th>" if labels else "") + "".join(
            f"<th{wd}>{e(c['label'])}</th>" for c, wd in zip(cols, widths, strict=True))
        thead = f"<thead><tr>{head}</tr></thead>" if look.get("header", True) else ""
        body = ""
        for r in rows:
            cells = ""
            for c in r["cells"]:
                c, _, rb, st = _styled(c, rules)
                cells += f"<td{_td(rb, st)}>{_value(c, big)}</td>"
            label = f"<th class='l'>{e(r['label'])}</th>" if labels else ""
            body += f"<tr>{label}{cells}</tr>"
        return f'<table class="{cls} grid"{style}>{thead}<tbody>{body}</tbody></table>'
    headers = look.get("headers") or (["Section", "Check", "Result"] if kind == "defects"
                                      else ["Check", "Result"])
    if kind == "defects":
        head = "".join(f"<th>{e(h)}</th>" for h in headers[:3])
        body = ""
        for r in rows:
            r, lt, rb, st = _styled(r, rules)
            td = _td(rb, st)
            label = f'<span class="{lt[1:]}">{e(r["label"])}</span>' if lt else e(r["label"])
            body += (f"<tr><td{td}>{e(r['section'])}</td><td{td}>{label}</td>"
                     f"<td{td}>{_value(r)}</td></tr>")
        thead = f"<thead><tr>{head}</tr></thead>" if look.get("header", True) else ""
        return f'<table class="{cls}"{style}>{thead}<tbody>{body}</tbody></table>'
    n = part.get("per_row", 1)
    lw = look.get("label_width", 55) / n
    vw = (100 - look.get("label_width", 55)) / n
    cg = "".join(f'<col style="width:{lw}%"><col style="width:{vw}%">' for _ in range(n))
    body = ""
    for i in range(0, len(rows), n):
        chunk = rows[i:i + n]
        cells = ""
        for r in chunk:
            r, lt, rb, st = _styled(r, rules)
            cells += f"<th class='l{lt}{rb}'{st}>{e(r['label'])}</th><td{_td(rb, st)}>{_value(r)}</td>"
        cells += "<td></td><td></td>" * (n - len(chunk))
        body += f"<tr>{cells}</tr>"
    head = ""
    if look.get("header", False):
        head = "<thead><tr>" + (f"<th>{e(headers[0])}</th><th>{e(headers[1])}</th>" * n) + \
            "</tr></thead>"
    return f'<table class="{cls}"{style}><colgroup>{cg}</colgroup>{head}<tbody>{body}</tbody></table>'


def _photos(part: dict, width_mm: float, edge: int) -> str:
    n = part.get("per_row", 2)
    frame = part.get("frame", {})
    gap = frame.get("gap", 4)
    cell = (width_mm - gap * (n - 1)) / n
    ratio = RATIO.get(part.get("shape", "4:3"))
    fit = part.get("fit", "fill")
    size = f"width:{cell:.2f}mm;" + (f"height:{cell * ratio:.2f}mm;" if ratio else "")
    obj = {"fill": "object-fit:cover", "whole": "object-fit:contain",
           "top": "object-fit:cover;object-position:top"}[fit]
    border = {"none": "", "grey": "border:0.3mm solid var(--line)",
              "brand": "border:0.3mm solid var(--brand)"}[frame.get("border", "none")]
    radius = "border-radius:1.5mm;" if frame.get("round", True) else ""
    figs = []
    for it in part["items"]:
        uri = print_image(it["media"], edge)
        img = (f'<img src="{uri}" style="{size}{obj};{border};{radius}">' if uri
               else f'<div class="noimg" style="{size}{radius}">Photo not available</div>')
        cap = ""
        if it["caption"]:
            answer = (f'<span class="ans tone-{it["tone"] or "text"}">{e(it["answer"])}</span>'
                      if it.get("answer") else "")
            cap = f"<figcaption><span>{e(it['caption'])}</span>{answer}</figcaption>"
        figs.append(f'<figure style="width:{cell:.2f}mm">{img}{cap}</figure>')
    return (f'<div class="photos" style="grid-template-columns:repeat({n},{cell:.2f}mm);'
            f'gap:{gap}mm">{"".join(figs)}</div>')


def part_html(part: dict, width_mm: float, ctx: dict) -> str:
    t = part["type"]
    if t == "page_break":
        return '<div class="pb"></div>'
    if t == "spacer":
        return f'<div style="height:{part.get("height", 10)}mm"></div>'
    title = (f'<h3 class="ptitle">{e(part["title"])}</h3>' if part.get("title") else "")
    keep = " keep" if part.get("keep_title", True) else ""
    if t == "table":
        inner = _table(part)
    elif t == "photos":
        pad = part.get("box", {}).get("padding", 0) * 2
        inner = _photos(part, width_mm - pad, ctx["edge"])
    elif t == "verify":
        size = part.get("size", 40)
        url = ctx["verify_url"]
        inner = (f'<div class="verify"><img src="{qr_uri(url)}" style="width:{size}mm;'
                 f'height:{size}mm"><div class="url">{e(url)}</div></div>')
    elif t == "columns":
        gap = part.get("gap", 6)
        cols = part["columns"]
        rest = 100 - sum(c.get("width", 0) for c in cols)
        free = sum(1 for c in cols if "width" not in c)
        cells = []
        for k, c in enumerate(cols):
            pct = c.get("width", rest / free if free else 0)
            inner_w = width_mm * pct / 100 - gap * (len(cols) - 1) / len(cols)
            pad = f"padding-left:{gap / 2}mm;" if k else ""
            pad += f"padding-right:{gap / 2}mm;" if k < len(cols) - 1 else ""
            body = "".join(part_html(p, inner_w, ctx) for p in c["parts"])
            cells.append(f'<td style="width:{pct:.2f}%;{pad}vertical-align:'
                         f'{part.get("align", "top")}">{body}</td>')
        inner = f'<table class="cols"><tr>{"".join(cells)}</tr></table>'
    elif t == "html":
        scope = f"custom-{len(ctx['css'])}"
        ctx["css"].append(f".{scope} {{ {part.get('css', '')} }}")    # nested: stays in this part
        inner = f'<div class="custom {scope}">{part["html_out"]}</div>'
    elif t == "contents":
        items = "".join(f'<li><a href="#{pid}">{e(name)}</a></li>' for pid, name in ctx["toc"])
        inner = f'<ol class="toc cols{part.get("columns", 1)}">{items}</ol>'
    else:
        cols = f" cols{part.get('columns', 1)}"
        inner = (f'<div class="text size-{part.get("size", "normal")}{cols}" '
                 f'style="text-align:{part.get("align", "left")}">{part["html_out"]}</div>')
    if t == "columns":
        keep += " together"
    pid = f' id="part-{e(part["id"])}"' if part.get("id") else ""
    return f'<section{pid} class="part{keep}" style="{_box(part)}">{title}{inner}</section>'


# ---------------------------------------------------------------- bands and page

def _slot(items: list[dict], values: dict) -> str:
    """Pictures and text side by side, centred on one line; texts next to each other stack."""
    out: list[str] = []
    texts: list[str] = []

    def flush():
        if texts:
            out.append(f'<span class="stack">{"".join(texts)}</span>')
            texts.clear()

    for it in items:
        if "text" in it:
            texts.append(f'<span class="line">{placeholders.render(it["text"], values)}</span>')
            continue
        flush()
        uri = asset_uri(it["image"])
        if uri:
            tile = " tile" if it.get("tile") else ""
            out.append(f'<img class="logo{tile}" src="{uri}" '
                       f'style="height:{it.get("height", 10)}mm">')
    flush()
    return f'<span class="slot">{"".join(out)}</span>'


def _band(name: str, band: dict, values: dict, margins: dict, page_w: float) -> str:
    brand = band.get("background", "none") == "brand"
    cls = "band brand" if brand else "band"
    cells = "".join(f'<td class="{side}">{_slot(band.get(side, []), values)}</td>'
                    for side in ("left", "center", "right"))
    # the band runs edge to edge: the full page width, pulled out over the side margins
    return (f'<div id="{name}" class="{cls}" style="width:{page_w}mm;'
            f'margin-left:-{margins["left"]}mm;padding:0 {margins["right"]}mm 0 '
            f'{margins["left"]}mm;height:{band.get("height", 16)}mm">'
            f'<table><tr>{cells}</tr></table></div>')


@cache
def font_faces() -> str:
    """The bundled fonts (SIL Open Font License, apps/reports/fonts) as data URIs."""
    out = []
    for family, weights in FONT_FILES.items():
        for w in weights:
            data = (FONTS_DIR / f"{family.replace(' ', '')}-{w}.ttf").read_bytes()
            uri = "data:font/ttf;base64," + base64.b64encode(data).decode()
            out.append(f'@font-face {{ font-family: "{family}"; font-weight: {w}; '
                       f'src: url({uri}) format("truetype") }}')
    return "\n".join(out)


def css(d: dict, colors: dict, margins: dict, bands: dict) -> str:
    paper = d.get("paper", {})
    orient = paper.get("orientation", "portrait")
    size = f"{paper.get('size', 'A4')} {orient}"
    tones = "".join(f"--{k}:{v};" for k, v in colors.items())
    tints = "".join(f"--{k}-tint:{v}1a;" for k, v in colors.items())
    fonts = d.get("theme", {}).get("fonts", {})
    body_font = STACK[fonts.get("body", "Inter")]
    head_font = STACK[fonts.get("headings", "Barlow Semi Condensed")]

    def page_rule(name: str) -> str:
        sel = "@page" if name == "normal" else f"@page {name}"
        if name == "full":                    # no bands: switch off what @page set up
            return f"{sel} {{ margin: 0; @top-center {{ content: none }} " \
                   f"@bottom-center {{ content: none }} }}"
        bs = bands.get(name, {})
        top = (bs.get("header", {}).get("height", 16) + 6) if "header" in bs else margins["top"]
        bottom = (bs.get("footer", {}).get("height", 10) + 4) if "footer" in bs \
            else margins["bottom"]
        # every page style says what its bands are (a named page would otherwise inherit them)
        head = f"element(h_{name})" if "header" in bs else "none"
        foot = f"element(f_{name})" if "footer" in bs else "none"
        boxes = (f"@top-center {{ content: {head}; width: 100%; vertical-align: top }}"
                 f"@bottom-center {{ content: {foot}; width: 100%; vertical-align: bottom }}")
        return (f"{sel} {{ margin: {top}mm {margins['right']}mm {bottom}mm {margins['left']}mm; "
                f"{boxes} }}")

    return f"""
{font_faces()}
@page {{ size: {size} }}
{page_rule("normal")} {page_rule("cover")} {page_rule("full")}
:root {{ {tones} {tints} --line: #d9dde3; --head: {head_font} }}
html {{ color: var(--text); font-family: {body_font};
  font-size: {d.get("theme", {}).get("size", 9.5)}pt; line-height: 1.38 }}
body {{ margin: 0 }}
.pg-normal {{ page: normal }} .pg-cover {{ page: cover }} .pg-full {{ page: full }}
.pg + .pg {{ break-before: page }}
h1, h2, h3, h4, h5, h6 {{ bookmark-level: none }}
.pg[data-title] {{ bookmark-level: 1; bookmark-label: attr(data-title) }}
.rb, .rb * {{ font-weight: 700 }}
.pb {{ break-after: page }}
#h_normal {{ position: running(h_normal) }} #h_cover {{ position: running(h_cover) }}
#f_normal {{ position: running(f_normal) }} #f_cover {{ position: running(f_cover) }}
.band {{ display: block; box-sizing: border-box; font-size: 8pt }}
.band table {{ width: 100%; height: 100%; border-collapse: collapse }}
.band td {{ vertical-align: middle; padding: 0 }} .band .center {{ text-align: center }}
.band .right {{ text-align: right }}
.band.brand {{ background: var(--brand); color: #fff }}
.slot {{ display: inline-flex; align-items: center; gap: 2.6mm; vertical-align: middle }}
.right .slot {{ justify-content: flex-end }}
.stack {{ display: inline-block; line-height: 1.15 }} .stack .line {{ display: block }}
.band strong {{ font-family: var(--head); font-weight: 700; letter-spacing: .06em; font-size: 1.35em }}
.band .large {{ font-family: var(--head); font-weight: 700; letter-spacing: .08em; font-size: 2.1em }}
.band .small {{ font-size: .8em; letter-spacing: .16em; opacity: .85 }}
.logo {{ display: block }} .logo.tile {{ background: #fff; border-radius: 1.4mm; padding: .8mm }}
.pageno::after {{ content: counter(page) }} .pages::after {{ content: counter(pages) }}
.part {{ display: block }}
.part.together {{ break-inside: avoid }}
.ptitle {{ font-size: .78em; font-weight: 700; text-transform: uppercase; letter-spacing: .08em;
  color: var(--muted); margin: 0 0 1mm; bookmark-level: 2 }}
.part.keep .ptitle {{ break-after: avoid }}
table.cols {{ width: 100%; border-collapse: collapse }} table.cols > tr > td, table.cols td {{ padding-top: 0 }}
table.t {{ width: 100%; border-collapse: collapse; page-break-inside: auto }}
table.t thead {{ display: table-header-group }} table.t tr {{ break-inside: avoid }}
table.t th, table.t td {{ padding: var(--pad) 1.6mm; text-align: left; vertical-align: top }}
table.t th.l {{ font-weight: 400; color: var(--text) }}
table.t thead th {{ font-size: .74em; font-weight: 600; text-transform: uppercase; letter-spacing: .06em;
  color: var(--muted); border-bottom: .45mm solid var(--text) }}
table.t.lines-rows td, table.t.lines-rows th.l {{ border-bottom: .2mm solid var(--line) }}
table.t.lines-all td, table.t.lines-all th {{ border: .2mm solid var(--line) }}
table.t.stripes tbody tr:nth-child(even) td, table.t.stripes tbody tr:nth-child(even) th {{ background: rgba(27,31,39,.035) }}
table.t.kv th.l {{ color: var(--muted) }} table.t.kv td {{ font-weight: 600 }}
table.t.emphasis {{ border: .2mm solid var(--line); border-radius: 1.5mm }}
table.t.emphasis th, table.t.emphasis td {{ text-align: center; vertical-align: middle; border: .2mm solid var(--line) }}
table.t.emphasis thead th {{ border-bottom: .2mm solid var(--line); color: var(--muted) }}
.big {{ font-family: var(--head); font-weight: 700; font-size: 2.2em; line-height: 1.1; display: block }}
.big small {{ font-size: .5em; color: var(--muted); font-weight: 500 }}
.dots {{ display: block; margin-top: .6mm }} .dots i {{ display: inline-block; width: 1.6mm; height: 1.6mm;
  border-radius: 50%; background: var(--ok); margin: 0 .35mm }} .dots i.off {{ background: var(--line) }}
.tone-ok {{ color: var(--ok); font-weight: 600 }} .tone-warn {{ color: var(--warn); font-weight: 600 }}
.tone-bad {{ color: var(--bad); font-weight: 600 }} .tone-muted {{ color: var(--muted) }}
.tone-brand {{ color: var(--brand) }} .tone-text {{ color: var(--text) }}
.chip {{ padding: .3mm 1.8mm; border-radius: 3mm; font-weight: 600 }}
.chip.tone-bad {{ background: var(--bad-tint) }} .chip.tone-warn {{ background: var(--warn-tint) }}
.chip.tone-ok {{ background: var(--ok-tint) }} .chip.tone-muted {{ background: var(--muted-tint) }}
.photos {{ display: grid }}
.photos figure {{ margin: 0; break-inside: avoid }}
.photos img {{ display: block; background: #eef0f3 }}
.photos figcaption {{ display: flex; justify-content: space-between; gap: 2mm; font-size: .85em;
  color: var(--text); margin-top: .8mm }}
.noimg {{ background: #eef0f3; color: var(--muted); display: flex; align-items: center; justify-content: center; font-size: .8em }}
.text.cols2 {{ columns: 2; column-gap: 6mm }}
.text.size-small {{ font-size: .85em }} .text.size-large {{ font-size: 1.25em }}
.text.size-title {{ font-family: var(--head); font-size: 3.4em; font-weight: 700; color: var(--brand); line-height: 1 }}
.text p {{ margin: 0 0 1.4mm }} .text ul, .text ol {{ margin: 0 0 1.4mm; padding-left: 5mm }}
.text h2 {{ font-family: var(--head); font-size: 1.55em; font-weight: 700; margin: 0 0 1.5mm;
  break-after: avoid }}
.text h2::before {{ content: ""; display: inline-block; width: 2.6mm; height: 2.6mm; margin-right: 1.6mm;
  border: .7mm solid var(--brand); border-radius: 50%; vertical-align: .1mm; box-sizing: border-box }}
.text h2 .small {{ font-size: .55em; font-weight: 500; color: var(--muted); margin-left: 2mm }}
.text h3 {{ font-family: var(--head); font-size: 1.2em; margin: 1.5mm 0 1mm }}
.text li {{ break-inside: avoid }}
.verify {{ text-align: center }} .verify img {{ display: block; margin: 0 auto }}
.verify .url {{ font-family: monospace; margin: 2.5mm auto 0; display: inline-block; padding: 1.4mm 3mm;
  background: rgba(27,31,39,.05); border-radius: 1.4mm }}
ol.toc {{ list-style: none; padding: 0; margin: 0 }} ol.toc.cols2 {{ columns: 2; column-gap: 10mm }}
ol.toc li {{ padding: 1mm 0; border-bottom: .2mm dotted var(--line); break-inside: avoid }}
ol.toc a {{ color: var(--text); text-decoration: none }}
ol.toc a::after {{ content: leader(" ") target-counter(attr(href), page); color: var(--muted) }}
"""


def render_html(pages: list[dict], d: dict, values: dict, *, edge: int = PRINT_EDGE) -> str:
    colors = {**COLORS, **d.get("theme", {}).get("colors", {})}
    paper = d.get("paper", {})
    w, h = PAPER[paper.get("size", "A4")]
    w = h if paper.get("orientation") == "landscape" else w
    margins = {**MARGINS, **paper.get("margins", {})}
    bands = d.get("bands", {})
    values = {**values, "sys": {**values["sys"], "page": Markup('<span class="pageno"></span>'),
                                "pages": Markup('<span class="pages"></span>')}}
    running = "".join(_band(f"{'h' if kind == 'header' else 'f'}_{style}", band, values, margins,
                            w) for style, bs in bands.items() for kind, band in bs.items())
    mark = ""
    wm = d.get("watermark")
    if wm and (uri := asset_uri(wm["image"], wm.get("opacity", 0.08))):
        size = wm.get("width", 60)
        mark = (f"@page {{ background: url({uri}) no-repeat center / {size}% auto }}"
                f"@page cover {{ background: url({uri}) no-repeat center / {size}% auto }}")
    width = w - margins["left"] - margins["right"]
    body = []
    custom: list[str] = []
    for n, page in enumerate(pages):
        style = page.get("style", "normal")
        # the contents list names the pages after this one that are not full-page designs
        toc = [(f"pg-{k}", p["title"]) for k, p in enumerate(pages)
               if k > n and p.get("style", "normal") != "full"]
        ctx = {"edge": edge, "verify_url": values["sys"]["verify_url"], "toc": toc, "css": custom}
        inner = "".join(part_html(p, w if style == "full" else width, ctx) for p in page["parts"])
        # each page is a bookmark in the PDF reader, its part titles under it
        mark_pg = f' data-title="{e(page["title"])}"' if page.get("title") else ""
        body.append(f'<div id="pg-{n}" class="pg pg-{style}"{mark_pg}>{inner}</div>')
    title = e(f"{values['sys']['booking_id']} {values['sys']['inspection_type']} report")
    return (f'<html><head><meta charset="utf-8"><title>{title}</title>'
            f'<meta name="generator" content="Vayu">'
            f'<style>{css(d, colors, margins, bands)}{mark}{"".join(custom)}</style></head>'
            f'<body>{running}{"".join(body)}</body></html>')


def _document(html_text: str):
    if sys.platform == "darwin" and os.path.isdir("/opt/homebrew/lib"):  # pragma: no cover
        os.environ.setdefault("DYLD_FALLBACK_LIBRARY_PATH", "/opt/homebrew/lib")
    from weasyprint import HTML
    from weasyprint.urls import URLFetcher

    # only data URIs, which we made ourselves: never a file or anything on the network
    return HTML(string=html_text, url_fetcher=URLFetcher(allowed_protocols={"data"})).render()


def render_pdf(html_text: str) -> bytes:
    return _document(html_text).write_pdf()


def render_with_layout(html_text: str) -> tuple[bytes, list[dict]]:
    """The PDF, and where each part with an id sits on each page (CSS px, top left origin), so
    the designer can highlight a part and pick one by clicking it."""
    doc = _document(html_text)
    pages = []
    for page in doc.pages:
        found: dict[str, list[float]] = {}
        for box in page._page_box.descendants():
            el = getattr(box, "element", None)
            pid = (el.get("id") or "") if el is not None and box.element_tag == "section" else ""
            if pid.startswith("part-"):
                r = found.setdefault(pid[5:], [1e9, 1e9, 0, 0])
                r[0], r[1] = min(r[0], box.position_x), min(r[1], box.position_y)
                r[2] = max(r[2], box.position_x + box.margin_width())
                r[3] = max(r[3], box.position_y + box.margin_height())
        pages.append({"width": page.width, "height": page.height, "parts": [
            {"id": k, "x": round(r[0], 1), "y": round(r[1], 1), "w": round(r[2] - r[0], 1),
             "h": round(r[3] - r[1], 1)} for k, r in found.items()]})
    return doc.write_pdf(), pages
