"""HTML and PDF for a report. WeasyPrint turns the HTML into pages: running header and footer
bands per page style, repeated table headers, page numbers. Every image is embedded by us as a
data URI, and the renderer loads nothing else (no files, no network)."""
import base64
import html
import io
import os
import sys
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


def _value(r: dict) -> str:
    if r.get("problem"):
        return f'<span class="chip tone-{r["tone"] or "bad"}">{e(r["text"])}</span>'
    tone = f' class="tone-{r["tone"]}"' if r.get("tone") else ""
    return f"<span{tone}>{e(r['text'])}</span>"


def _table(part: dict) -> str:
    look = part.get("look", {})
    kind = part["source"]["kind"]
    cls = (f"t lines-{look.get('lines', 'rows')}" + (" stripes" if look.get("stripes", True) else ""))
    pad = PADS[look.get("height", "normal")]
    style = f' style="--pad:{pad}mm"'
    rows = part["rows"]
    if kind == "grid":
        cols = part["source"]["columns"]
        widths = [f' style="width:{c["width"]}%"' if c.get("width") else "" for c in cols]
        head = "<th></th>" + "".join(f"<th{wd}>{e(c['label'])}</th>"
                                     for c, wd in zip(cols, widths, strict=True))
        body = "".join("<tr><th class='l'>" + e(r["label"]) + "</th>" + "".join(
            f"<td>{_value(c)}</td>" for c in r["cells"]) + "</tr>" for r in rows)
        return f'<table class="{cls} grid"{style}><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'
    headers = look.get("headers") or (["Section", "Check", "Result"] if kind == "defects"
                                      else ["Check", "Result"])
    if kind == "defects":
        head = "".join(f"<th>{e(h)}</th>" for h in headers[:3])
        body = "".join(f"<tr><td>{e(r['section'])}</td><td>{e(r['label'])}</td>"
                       f"<td>{_value(r)}</td></tr>" for r in rows)
        thead = f"<thead><tr>{head}</tr></thead>" if look.get("header", True) else ""
        return f'<table class="{cls}"{style}>{thead}<tbody>{body}</tbody></table>'
    n = part.get("per_row", 1)
    lw = look.get("label_width", 55) / n
    vw = (100 - look.get("label_width", 55)) / n
    cg = "".join(f'<col style="width:{lw}%"><col style="width:{vw}%">' for _ in range(n))
    body = ""
    for i in range(0, len(rows), n):
        chunk = rows[i:i + n]
        cells = "".join(f"<th class='l'>{e(r['label'])}</th><td>{_value(r)}</td>" for r in chunk)
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
        cap = f"<figcaption>{e(it['caption'])}</figcaption>" if it["caption"] else ""
        figs.append(f"<figure>{img}{cap}</figure>")
    return (f'<div class="photos" style="grid-template-columns:repeat({n},{cell:.2f}mm);'
            f'gap:{gap}mm">{"".join(figs)}</div>')


def part_html(part: dict, width_mm: float, edge: int, verify_url: str) -> str:
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
        inner = _photos(part, width_mm - pad, edge)
    elif t == "verify":
        size = part.get("size", 40)
        inner = (f'<div class="verify"><img src="{qr_uri(verify_url)}" style="width:{size}mm;'
                 f'height:{size}mm"><div class="url">{e(verify_url)}</div></div>')
    else:
        cols = f" cols{part.get('columns', 1)}"
        inner = (f'<div class="text size-{part.get("size", "normal")}{cols}" '
                 f'style="text-align:{part.get("align", "left")}">{part["html_out"]}</div>')
    return f'<section class="part{keep}" style="{_box(part)}">{title}{inner}</section>'


# ---------------------------------------------------------------- bands and page

def _slot(items: list[dict], values: dict) -> str:
    out = []
    for it in items:
        if "text" in it:
            out.append(f"<div>{placeholders.render(it['text'], values)}</div>")
        else:
            uri = asset_uri(it["image"])
            if uri:
                out.append(f'<img src="{uri}" style="height:{it.get("height", 10)}mm">')
    return "".join(out)


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


def css(d: dict, colors: dict, margins: dict, bands: dict) -> str:
    paper = d.get("paper", {})
    orient = paper.get("orientation", "portrait")
    size = f"{paper.get('size', 'A4')} {orient}"
    tones = "".join(f"--{k}:{v};" for k, v in colors.items())
    tints = "".join(f"--{k}-tint:{v}1a;" for k, v in colors.items())

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
@page {{ size: {size} }}
{page_rule("normal")} {page_rule("cover")} {page_rule("full")}
:root {{ {tones} {tints} --line: #d9dde3 }}
html {{ color: var(--text); font-family: Helvetica, Arial, sans-serif;
  font-size: {d.get("theme", {}).get("size", 9.5)}pt; line-height: 1.35 }}
body {{ margin: 0 }}
.pg-normal {{ page: normal }} .pg-cover {{ page: cover }} .pg-full {{ page: full }}
.pg + .pg {{ break-before: page }}
.pb {{ break-after: page }}
#h_normal {{ position: running(h_normal) }} #h_cover {{ position: running(h_cover) }}
#f_normal {{ position: running(f_normal) }} #f_cover {{ position: running(f_cover) }}
.band {{ display: block; box-sizing: border-box }} .band table {{ width: 100%; height: 100%; border-collapse: collapse }}
.band td {{ vertical-align: middle; padding: 0 }} .band .center {{ text-align: center }} .band .right {{ text-align: right }}
.band.brand {{ background: var(--brand); color: #fff }}
.pageno::after {{ content: counter(page) }} .pages::after {{ content: counter(pages) }}
.part {{ display: block }}
.ptitle {{ font-size: 1.35em; margin: 0 0 1.5mm; color: var(--text); bookmark-level: 2 }}
.part.keep .ptitle {{ break-after: avoid }}
table.t {{ width: 100%; border-collapse: collapse; page-break-inside: auto }}
table.t thead {{ display: table-header-group }} table.t tr {{ break-inside: avoid }}
table.t th, table.t td {{ padding: var(--pad) 1.6mm; text-align: left; vertical-align: top }}
table.t th.l {{ font-weight: 400; color: var(--text) }}
table.t thead th {{ font-size: .8em; text-transform: uppercase; letter-spacing: .05em; color: var(--muted);
  border-bottom: .4mm solid var(--text) }}
table.t.lines-rows td, table.t.lines-rows th.l {{ border-bottom: .2mm solid var(--line) }}
table.t.lines-all td, table.t.lines-all th {{ border: .2mm solid var(--line) }}
table.t.stripes tbody tr:nth-child(even) td, table.t.stripes tbody tr:nth-child(even) th {{ background: rgba(27,31,39,.035) }}
table.t.grid thead th {{ text-align: left }}
.tone-ok {{ color: var(--ok); font-weight: 600 }} .tone-warn {{ color: var(--warn); font-weight: 600 }}
.tone-bad {{ color: var(--bad); font-weight: 600 }} .tone-muted {{ color: var(--muted) }}
.tone-brand {{ color: var(--brand) }} .tone-text {{ color: var(--text) }}
.chip {{ padding: .3mm 1.6mm; border-radius: 3mm; font-weight: 600 }}
.chip.tone-bad {{ background: var(--bad-tint) }} .chip.tone-warn {{ background: var(--warn-tint) }}
.chip.tone-ok {{ background: var(--ok-tint) }} .chip.tone-muted {{ background: var(--muted-tint) }}
.photos {{ display: grid }}
.photos figure {{ margin: 0; break-inside: avoid }}
.photos img {{ display: block; background: #eef0f3 }}
.photos figcaption {{ font-size: .85em; color: var(--text); margin-top: .8mm }}
.noimg {{ background: #eef0f3; color: var(--muted); display: flex; align-items: center; justify-content: center; font-size: .8em }}
.text.cols2 {{ columns: 2; column-gap: 6mm }}
.text.size-small {{ font-size: .85em }} .text.size-large {{ font-size: 1.25em }}
.text.size-title {{ font-size: 2.6em; font-weight: 700; color: var(--brand); line-height: 1.05 }}
.text p {{ margin: 0 0 1.4mm }} .text ul, .text ol {{ margin: 0 0 1.4mm; padding-left: 5mm }}
.text h2 {{ font-size: 1.5em; margin: 0 0 1.5mm; bookmark-level: 1 }} .text h3 {{ font-size: 1.2em; margin: 1.5mm 0 1mm }}
.text li {{ break-inside: avoid }}
.verify {{ text-align: center }} .verify .url {{ font-family: monospace; margin-top: 2mm }}
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
    for page in pages:
        style = page.get("style", "normal")
        inner = "".join(part_html(p, w if style == "full" else width, edge,
                                  values["sys"]["verify_url"]) for p in page["parts"])
        body.append(f'<div class="pg pg-{style}">{inner}</div>')
    title = e(f"{values['sys']['booking_id']} {values['sys']['inspection_type']} report")
    return (f'<html><head><meta charset="utf-8"><title>{title}</title>'
            f'<style>{css(d, colors, margins, bands)}{mark}</style></head>'
            f'<body>{running}{"".join(body)}</body></html>')


def render_pdf(html_text: str) -> bytes:
    if sys.platform == "darwin" and os.path.isdir("/opt/homebrew/lib"):  # pragma: no cover
        os.environ.setdefault("DYLD_FALLBACK_LIBRARY_PATH", "/opt/homebrew/lib")
    from weasyprint import HTML
    from weasyprint.urls import URLFetcher

    # only data URIs, which we made ourselves: never a file or anything on the network
    return HTML(string=html_text, url_fetcher=URLFetcher(allowed_protocols={"data"})).write_pdf()
