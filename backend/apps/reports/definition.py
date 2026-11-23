"""PDF template definition (schema 2): pages of parts, checked against schema.json and then for
the things a schema cannot say (rules, placeholders, unique ids). docs/plan-reports.md."""
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

from apps.forms.rules import rule_syntax_issues

from . import placeholders

SCHEMA = json.loads((Path(__file__).parent / "schema.json").read_text())
_validator = Draft202012Validator(SCHEMA)
OLD = ("This template was made for the old report designer; build it again with the new "
       "one.")


def _where(path) -> str:
    text = "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in path)
    return text.lstrip(".") or "template"


def _walk(items: list, path: str) -> Iterator[tuple[str, dict]]:
    for j, part in enumerate(items):
        yield f"{path}[{j}]", part
        for c, col in enumerate(part.get("columns", []) if part.get("type") == "columns" else []):
            yield from _walk(col.get("parts", []), f"{path}[{j}].columns[{c}].parts")


def parts(d: dict) -> Iterator[tuple[str, dict]]:
    """Every part of every page, the parts inside columns too."""
    for i, page in enumerate(d.get("pages", [])):
        yield from _walk(page.get("parts", []), f"pages[{i}].parts")


def texts(d: dict) -> Iterator[tuple[str, str]]:
    """(where, text) of everything that may hold placeholders."""
    if "filename" in d:
        yield "filename", d["filename"]
    for style, bandset in d.get("bands", {}).items():
        for band, slots in bandset.items():
            for side in ("left", "center", "right"):
                for k, item in enumerate(slots.get(side, [])):
                    if "text" in item:
                        yield f"bands.{style}.{band}.{side}[{k}]", item["text"]
    for where, p in parts(d):
        if p["type"] == "text":
            yield f"{where}.html", p["html"]
        if p["type"] == "photos" and "caption_text" in p:
            yield f"{where}.caption_text", p["caption_text"]
        if p["type"] == "table" and p["source"]["kind"] == "grid":
            for r, row in enumerate(p["source"]["rows"]):
                yield f"{where}.source.rows[{r}].label", row["label"]
                for c, cell in enumerate(row["cells"]):
                    if "text" in cell:
                        yield f"{where}.source.rows[{r}].cells[{c}]", cell["text"]


def rules(d: dict) -> Iterator[tuple[str, Any]]:
    for i, page in enumerate(d.get("pages", [])):
        yield f"pages[{i}].show_if", page.get("show_if")
    for where, p in parts(d):
        yield f"{where}.show_if", p.get("show_if")
        src = p.get("source", {})
        for r, row in enumerate(src.get("rows", [])):
            yield f"{where}.source.rows[{r}].show_if", row.get("show_if")


def validate_definition(d: Any) -> dict:
    """Raises ValueError. Returns the definition with its rich text cleaned."""
    if isinstance(d, dict) and "blocks" in d and "schema" not in d:
        raise ValueError(OLD)
    error = best_match(_validator.iter_errors(d))
    if error is not None:
        raise ValueError(f"{_where(error.absolute_path)}: {error.message}")
    for _, p in parts(d):
        if p["type"] == "text":
            p["html"] = placeholders.clean_html(p["html"])
    for bandset in d.get("bands", {}).values():
        for band in bandset.values():
            for side in ("left", "center", "right"):
                for item in band.get(side, []):
                    if "text" in item:
                        item["text"] = placeholders.clean_html(item["text"])
    for where, text in texts(d):
        placeholders.check(text, where)
    for where, rule in rules(d):
        if issues := rule_syntax_issues(rule, where):
            raise ValueError(issues[0].message)
    ids = [x["id"] for x in d["pages"] if "id" in x] + [p["id"] for _, p in parts(d) if "id" in p]
    if len(ids) != len(set(ids)):
        raise ValueError("Two pages or parts share an id.")
    return d


def field_ref(ref: str) -> tuple[str, str]:
    """'inspection.door' -> ('inspection', 'door')."""
    form, _, key = ref.partition(".")
    return form, key


def referenced_fields(d: dict) -> set[tuple[str, str]]:
    """Every (form, key) the template names directly (a whole section is in referenced_sections)."""
    refs: set[tuple[str, str]] = set()
    for _, text in texts(d):
        refs |= placeholders.refs(text)
    for _, p in parts(d):
        src = p.get("source", {})
        for row in src.get("rows", []):
            if "field" in row:
                refs.add(field_ref(row["field"]))
            for cell in row.get("cells", []):
                if "field" in cell:
                    refs.add(field_ref(cell["field"]))
        for f in src.get("fields", []):
            refs.add(field_ref(f))
        for k in src.get("exclude", []):
            refs.add(("inspection", k))
    return refs


def referenced_sections(d: dict) -> set[str]:
    return {p["source"]["section"].split(".", 1)[1] for _, p in parts(d)
            if p.get("source", {}).get("kind") == "section"}


def filename_for(d: dict, values: dict) -> str:
    name = placeholders.render(d.get("filename", "{{ sys.booking_id }}.pdf"), values, html=False)
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return name if name.endswith(".pdf") else f"{name}.pdf"
