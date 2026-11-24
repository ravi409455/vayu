"""A report template as one file: its layout, the shared theme and parts it uses, and its
pictures. Export is a backup; import puts everything in the file into the template's draft
(the draft is replaced). Promotion bundles (apps/forms/promote.py) carry the same thing.

Nothing is matched by id across servers: pictures are stored again (once: the same picture
already here is reused) and shared items are matched by key."""
import copy
from typing import Any

from django.db import transaction

from apps.accounts import audit
from apps.bookings.services import err
from apps.forms import assets
from apps.forms.models import FormAsset

from . import shared
from .models import PdfTemplate, PdfTemplateVersion, SharedItem, SharedRevision

FILE_KIND = "vayu-report-template"
SCHEMA = 2


def _images(obj: Any) -> set[str]:
    """Every picture id a definition or shared content uses ({"image": id})."""
    out: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "image" and isinstance(v, str):
                out.add(v)
            else:
                out |= _images(v)
    elif isinstance(obj, list):
        for v in obj:
            out |= _images(v)
    return out


def _remap(obj: Any, mapping: dict[str, str]) -> Any:
    if isinstance(obj, dict):
        return {k: (mapping.get(v, v) if k == "image" and isinstance(v, str)
                    else _remap(v, mapping)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_remap(v, mapping) for v in obj]
    return obj


def export_payload(definition: dict) -> dict:
    """The layout with every shared item and picture it needs."""
    items: list[dict] = []
    for kind, _, ref in shared.refs(definition):
        r = SharedRevision.objects.filter(item__kind=kind, item__key=ref["key"],
                                          revision=ref["revision"]).select_related("item").first()
        if r is not None and not any(i["kind"] == kind and i["key"] == ref["key"] for i in items):
            items.append({"kind": kind, "key": ref["key"], "name": r.item.name,
                          "revision": r.revision, "content": r.content})
    ids = _images(definition) | _images([i["content"] for i in items])
    return {"definition": definition, "shared": items,
            "assets": {str(a.id): assets.export(a) for a in FormAsset.objects.filter(pk__in=ids)}}


def export_file(v: PdfTemplateVersion) -> dict:
    return {"kind": FILE_KIND, "schema": SCHEMA, "form": v.template.form.key,
            "version": v.number, **export_payload(v.definition)}


def _shared_in(actor, items: list, notes: list[str]) -> dict[tuple, int]:
    """(kind, key, revision in the file) -> revision here. A new item is created; an item that
    exists keeps its content (the file's is used only if it matches one of its revisions)."""
    out: dict[tuple, int] = {}
    for it in items:
        kind, key = it["kind"], it["key"]
        content = shared.check_content(kind, it["content"])
        item = SharedItem.objects.filter(kind=kind, key=key).first()
        if item is None:
            item = SharedItem.objects.create(kind=kind, key=key, name=str(it["name"])[:100],
                                             revision=1)
            SharedRevision.objects.create(item=item, revision=1, content=content,
                                          created_by=actor)
            out[(kind, key, it["revision"])] = 1
            continue
        same = next((r.revision for r in item.revisions.order_by("-revision")
                     if r.content == content), None)
        if same is None:
            notes.append(f"The shared {'theme' if kind == 'theme' else 'part'} '{item.name}' "
                         f"is different here; kept this server's version {item.revision}.")
        out[(kind, key, it["revision"])] = same or item.revision
    return out


def load_payload(actor, payload: Any) -> tuple[dict, list[str]]:
    """The file's layout ready for this server (pictures stored, shared items matched), and
    notes on what was kept. Raises ValueError on a damaged file; call inside a transaction."""
    from .definition import validate_definition

    if not isinstance(payload, dict) or not isinstance(payload.get("definition"), dict) \
            or not isinstance(payload.get("shared", []), list) \
            or not isinstance(payload.get("assets", {}), dict):
        raise ValueError("This is not a Vayu report template file.")
    notes: list[str] = []
    try:
        pictures = {old: str(assets.import_from_bundle(actor, p, library=True).id)
                    for old, p in payload.get("assets", {}).items()}
        items = [{**i, "content": _remap(i["content"], pictures)}
                 for i in payload.get("shared", [])]
        revisions = _shared_in(actor, items, notes)
    except (KeyError, TypeError) as e:
        raise ValueError("A shared theme or part in the file is damaged.") from e
    d = validate_definition(_remap(copy.deepcopy(payload["definition"]), pictures))
    for kind, _, ref in shared.refs(d):
        ref["revision"] = revisions.get((kind, ref["key"], ref["revision"]), ref["revision"])
    return d, notes


def import_file(actor, t: PdfTemplate, payload: Any) -> dict:
    """Put the file into the template's draft (made if there is none). What the file uses that
    this form lacks comes back as issues: publishing stays blocked until each is fixed."""
    from .service import definition_issues

    if not isinstance(payload, dict) or payload.get("kind") != FILE_KIND:
        raise err("INVALID_TEMPLATE_FILE", "This is not a Vayu report template file.")
    if payload.get("schema") != SCHEMA:
        raise err("INVALID_TEMPLATE_FILE", "This file was made by another version of Vayu.")
    with transaction.atomic():
        try:
            d, notes = load_payload(actor, payload)
        except ValueError as e:
            raise err("INVALID_TEMPLATE_FILE", str(e)) from e
        draft = t.versions.select_for_update().filter(status="draft").first()
        if draft is None:
            last = t.versions.order_by("-number").first()
            draft = PdfTemplateVersion.objects.create(
                template=t, number=(last.number + 1) if last else 1, definition=d)
        else:
            draft.definition, draft.row_version = d, draft.row_version + 1
            draft.save()
        audit.record(actor, "pdf_template.import", "pdf_template", t.id,
                     f"Imported a template file into {t.form.key} draft v{draft.number}")
    return {"version": draft, "issues": definition_issues(t, d), "notes": notes}


def copy_template(actor, source: PdfTemplateVersion, form) -> PdfTemplate:
    """A new template for another inspection form, starting from this layout as its draft."""
    from .service import create_template

    with transaction.atomic():
        t = create_template(actor, form)
        draft = t.versions.get(status="draft")
        draft.definition = copy.deepcopy(source.definition)
        draft.save()
        audit.record(actor, "pdf_template.copy", "pdf_template", t.id,
                     f"Copied from {source.template.form.key} v{source.number}")
    return t
