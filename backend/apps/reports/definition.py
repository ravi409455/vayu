"""PDF template definition: an ordered list of blocks, validated before it is saved."""
import re
from typing import Any

from apps.forms.rules import rule_syntax_issues

BLOCK_TYPES = ("cover", "table", "ratings", "documents", "photos", "heading", "text",
               "page_break", "spacer")
FILENAME_TOKENS = {"booking_id", "type_code", "date"}
FONT_SIZES = ("small", "medium", "large")
HEX = re.compile(r"#[0-9a-fA-F]{6}")
COMMON = {"type", "show_if", "font_size"}
ALLOWED = {
    "cover": COMMON | {"photo", "rows"}, "table": COMMON | {"title", "rows"},
    "ratings": COMMON | {"title"}, "documents": COMMON | {"title", "rows"},
    "photos": COMMON | {"title", "columns", "items"}, "heading": COMMON | {"text"},
    "text": COMMON | {"text"}, "page_break": {"type"}, "spacer": {"type", "height"},
}


def field_ref(ref: str) -> tuple[str, str]:
    """'inspection.door' -> ('inspection', 'door'); a bare key means the inspection form."""
    form, _, key = ref.rpartition(".")
    return (form or "inspection", key)


def _rows(rows: Any, path: str) -> None:
    if not isinstance(rows, list):
        raise ValueError(f"{path}.rows must be a list.")
    for r in rows:
        if (not isinstance(r, dict) or set(r) - {"label", "field"}
                or not isinstance(r.get("label"), str) or not r["label"].strip()
                or not isinstance(r.get("field"), str)):
            raise ValueError(f"{path}: each row needs a label and a field.")


def validate_definition(d: Any) -> None:
    """Raises ValueError. An empty definition is valid (a blank report)."""
    if not isinstance(d, dict) or set(d) - {"filename", "type_code", "branding", "blocks"}:
        raise ValueError("A template holds filename, type_code, branding and blocks.")
    pattern = d.get("filename", "{booking_id}{type_code}.pdf")
    if not isinstance(pattern, str) or not pattern.endswith(".pdf") or \
            set(re.findall(r"\{(\w+)\}", pattern)) - FILENAME_TOKENS \
            or "/" in pattern or "\\" in pattern:
        raise ValueError(f"filename must end in .pdf and may use {sorted(FILENAME_TOKENS)}.")
    if not isinstance(d.get("type_code", ""), str):
        raise ValueError("type_code must be text.")
    b = d.get("branding", {})
    if not isinstance(b, dict) or set(b) - {"title", "color", "watermark", "logo"}:
        raise ValueError("branding holds title, color, watermark and logo.")
    if "color" in b and not HEX.fullmatch(str(b["color"])):
        raise ValueError("branding.color must look like #a62830.")
    if "watermark" in b and not isinstance(b["watermark"], bool):
        raise ValueError("branding.watermark must be true or false.")
    blocks = d.get("blocks", [])
    if not isinstance(blocks, list):
        raise ValueError("blocks must be a list.")
    for i, blk in enumerate(blocks):
        path = f"blocks[{i}]"
        if not isinstance(blk, dict) or blk.get("type") not in BLOCK_TYPES:
            raise ValueError(f"{path}: type must be one of {', '.join(BLOCK_TYPES)}.")
        if set(blk) - ALLOWED[blk["type"]]:
            raise ValueError(f"{path}: unknown properties for a {blk['type']} block.")
        if blk.get("font_size", "medium") not in FONT_SIZES:
            raise ValueError(f"{path}: font_size must be one of {', '.join(FONT_SIZES)}.")
        if issues := rule_syntax_issues(blk.get("show_if"), f"{path}.show_if"):
            raise ValueError(issues[0].message)
        if blk["type"] in ("cover", "table", "documents"):
            _rows(blk.get("rows", []), path)
        if blk["type"] == "cover" and "photo" in blk and not isinstance(blk["photo"], str):
            raise ValueError(f"{path}.photo must be a field reference.")
        if blk["type"] == "photos":
            if blk.get("columns", 2) not in (1, 2, 3):
                raise ValueError(f"{path}.columns must be 1, 2 or 3.")
            items = blk.get("items", [])
            if not isinstance(items, list) or any(
                    not isinstance(x, dict) or set(x) - {"field", "index", "caption"}
                    or not isinstance(x.get("field"), str)
                    or not isinstance(x.get("index", 0), int) or isinstance(x.get("index"), bool)
                    for x in items):
                raise ValueError(f"{path}.items need a field (and optional index, caption).")
        if blk["type"] in ("heading", "text") and not isinstance(blk.get("text", ""), str):
            raise ValueError(f"{path}.text must be text.")
        if blk["type"] == "spacer" and not (isinstance(blk.get("height", 10), int)
                                            and 1 <= blk.get("height", 10) <= 200):
            raise ValueError(f"{path}.height must be 1-200.")


def referenced_fields(d: dict) -> set[tuple[str, str]]:
    refs: set[tuple[str, str]] = set()
    for blk in d.get("blocks", []):
        for row in blk.get("rows", []):
            refs.add(field_ref(row["field"]))
        for item in blk.get("items", []):
            refs.add(field_ref(item["field"]))
        if blk.get("photo"):
            refs.add(field_ref(blk["photo"]))
    return refs


def filename_for(d: dict, booking_id: str, day: str) -> str:
    pattern = d.get("filename", "{booking_id}{type_code}.pdf")
    name = pattern.format(booking_id=booking_id, type_code=d.get("type_code", ""), date=day)
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)
