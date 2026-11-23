"""HTML and PDF for a report. WeasyPrint turns the HTML into paged PDF (page numbers, footer)."""
import base64
import html
import io
import os
import sys

import qrcode
from django.conf import settings

from apps.media import storage
from apps.media.models import MediaAsset

SIZES = {"small": "9pt", "medium": "11pt", "large": "14pt"}
BAD = "#b3261e"


def qr_uri(text: str) -> str:
    buf = io.BytesIO()
    qrcode.make(text, box_size=4, border=1).save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def image_uri(media_id: str | None) -> str | None:
    asset = MediaAsset.objects.filter(pk=media_id, status="verified").first() if media_id else None
    if asset is None:
        return None
    return (f"data:{asset.content_type};base64,"
            + base64.b64encode(storage.read(asset.key)).decode())


def e(s) -> str:
    return html.escape(str(s))


def _rows(rows) -> str:
    out = []
    for r in rows:
        style = f' style="color:{BAD}"' if r["defect"] else ""
        out.append(f'<tr><th>{e(r["label"])}</th><td{style}>{e(r["text"])}</td></tr>')
    return "<table class='rows'>" + "".join(out) + "</table>"


def block_html(b: dict) -> str:
    size = SIZES[b["font_size"]]
    t = b["type"]
    wrap = f'<section style="font-size:{size}">'
    if t == "page_break":
        return '<div style="page-break-after:always"></div>'
    if t == "spacer":
        return f'<div style="height:{int(b["height"])}px"></div>'
    if t == "heading":
        return f'{wrap}<h2>{e(b["text"])}</h2></section>'
    if t == "text":
        return f'{wrap}<p>{e(b["text"])}</p></section>'
    if t == "cover":
        img = image_uri(b.get("photo"))
        pic = f'<img class="hero" src="{img}">' if img else '<div class="hero"></div>'
        return f'{wrap}<div class="cover">{pic}<div>{_rows(b["rows"])}</div></div></section>'
    if t == "ratings":
        head = f'<h2>{e(b["title"] or "Overall Rating")}</h2>'
        row = "".join(f'<td><b>{e(r["label"])}</b><br>{e(r["text"])}</td>' for r in b["rows"])
        return (f'{wrap}{head}<table class="ratings"><tr>{row}<td><b>Expert Rating</b><br>'
                f'{e(b["overall"])}</td></tr></table></section>')
    if t == "photos":
        cells = []
        for it in b["items"]:
            img = image_uri(it["media"])
            body = f'<img src="{img}">' if img else '<div class="empty"></div>'
            cells.append(f'<div class="cell" style="width:{100 // b["columns"] - 2}%">{body}'
                         f'<div class="cap">{e(it["caption"])}</div></div>')
        return f'{wrap}<h2>{e(b["title"])}</h2><div class="grid">{"".join(cells)}</div></section>'
    return f'{wrap}<h2>{e(b["title"])}</h2>{_rows(b["rows"])}</section>'   # table, documents


CSS = """
@page { size: A4; margin: 28mm 14mm 18mm 14mm;
  @top-center { content: element(header) }
  @bottom-left { content: element(stampbox) }
  @bottom-right { content: "Page " counter(page) " of " counter(pages); font-size: 8pt; color: #555 } }
body { font-family: Helvetica, Arial, sans-serif; color: #111 }
#header { position: running(header); color: white; padding: 8px 14px; font-size: 13pt }
#stampbox { position: running(stampbox); font-size: 8pt; color: #555 }
table.rows { width: 100%; border-collapse: collapse } table.rows th { text-align: left; width: 45%; }
table.rows th, table.rows td { border: 1px solid #999; padding: 4px 6px }
table.ratings { width: 100%; border-collapse: collapse; text-align: center }
table.ratings td { border: 1px solid #999; padding: 6px }
.cover { display: flex; gap: 12px } .hero { width: 45%; height: 180px; background: #eee }
.grid { display: flex; flex-wrap: wrap; gap: 8px } .cell img { width: 100%; }
.cap { text-align: center; font-size: 9pt } .empty { height: 120px; background: #eee }
.watermark { position: fixed; top: 40%; left: 15%; font-size: 70pt; color: rgba(0,0,0,.05);
  transform: rotate(-30deg) }
"""


def render_html(blocks: list[dict], definition: dict, *, booking_id: str, revision: int,
                stamp: str, token: str) -> str:
    brand = definition.get("branding", {})
    color = brand.get("color", "#a62830")
    title = brand.get("title", "CAR INSPECTION REPORT")
    qr = qr_uri(f"{settings.VERIFY_BASE_URL}/{token}")
    mark = '<div class="watermark">CAR C.I.D.</div>' if brand.get("watermark") else ""
    return (f'<html><head><meta charset="utf-8"><style>{CSS}</style></head><body>'
            f'<div id="header" style="background:{color}">{e(title)} &nbsp; <small>{e(booking_id)}'
            f'</small></div><div id="stampbox">Generated {e(stamp)}, rev {revision}</div>{mark}'
            + "".join(block_html(b) for b in blocks)
            + f'<div style="margin-top:12px"><img src="{qr}" width="70"> <small style="font-size:8pt;white-space:nowrap">'
            f'Verify this report: {e(settings.VERIFY_BASE_URL)}/{e(token)}</small></div></body></html>')


def render_pdf(html_text: str) -> bytes:
    if sys.platform == "darwin" and os.path.isdir("/opt/homebrew/lib"):  # pragma: no cover
        os.environ.setdefault("DYLD_FALLBACK_LIBRARY_PATH", "/opt/homebrew/lib")
    from weasyprint import HTML

    return HTML(string=html_text).write_pdf()
