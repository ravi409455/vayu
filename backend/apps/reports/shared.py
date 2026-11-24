"""Shared themes and shared parts. A template points at one revision of each
(`"theme_ref": {"key": "carcid", "revision": 3}`, a part `{"type": "snippet", "ref": ...}`);
`resolve` puts their content in before a render. Saving a shared item makes a new revision and
moves every template that uses it onto that revision (the live one republished, the draft
updated), so a change to the disclaimer is made once."""
import copy
from collections.abc import Iterator

from django.db import transaction
from django.utils import timezone

from apps.accounts import audit
from apps.bookings.services import err

from .definition import KEY_RE, parts, validate_definition
from .models import PdfTemplate, PdfTemplateVersion, SharedItem, SharedRevision

THEME_KEYS = ("theme", "bands", "watermark")
KINDS = ("theme", "snippet")


def _content(kind: str, ref: dict, cache: dict) -> dict | None:
    k = (kind, ref["key"], ref["revision"])
    if k not in cache:
        r = SharedRevision.objects.filter(item__kind=kind, item__key=ref["key"],
                                          revision=ref["revision"]).first()
        cache[k] = r.content if r else None
    return cache[k]


def _strip_ids(items: list) -> list:
    """A shared part may be used twice in one template: its own parts carry no ids."""
    out = []
    for p in items:
        q = {k: v for k, v in p.items() if k != "id"}
        if q["type"] == "columns":
            q["columns"] = [{**c, "parts": _strip_ids(c["parts"])} for c in q["columns"]]
        out.append(q)
    return out


def resolve(d: dict) -> dict:
    """The definition with its theme's settings and its shared parts' content filled in. A
    reference that does not exist resolves to nothing (definition_issues reports it)."""
    cache: dict = {}
    out = copy.deepcopy(d)
    if ref := out.get("theme_ref"):
        theme = _content("theme", ref, cache) or {}
        for k in THEME_KEYS:
            out.pop(k, None)
            if k in theme:
                out[k] = copy.deepcopy(theme[k])
    for _, p in parts(out):
        if p["type"] == "snippet":
            snippet = _content("snippet", p["ref"], cache) or {"parts": []}
            p["parts"] = _strip_ids(copy.deepcopy(snippet["parts"]))
    return out


def refs(d: dict) -> Iterator[tuple[str, str, dict]]:
    """(kind, where, ref) of every shared item a definition points at."""
    if "theme_ref" in d:
        yield "theme", "theme_ref", d["theme_ref"]
    for where, p in parts(d):
        if p["type"] == "snippet":
            yield "snippet", where, p["ref"]


def missing(d: dict) -> list[dict]:
    cache: dict = {}
    return [{"path": where, "part": None if kind == "theme" else _part_id(d, where),
             "code": "UNKNOWN_SHARED",
             "message": f"The shared {'theme' if kind == 'theme' else 'part'} '{ref['key']}' "
                        f"version {ref['revision']} is not on this server."}
            for kind, where, ref in refs(d) if _content(kind, ref, cache) is None]


def _part_id(d: dict, where: str) -> str | None:
    return next((p.get("id") for w, p in parts(d) if w == where), None)


def check_content(kind: str, content) -> dict:
    """Raises ValueError. A theme holds colours and fonts, header and footer, watermark; a shared
    part holds parts (never another shared part, so they cannot loop)."""
    if kind == "theme":
        if not isinstance(content, dict) or set(content) - set(THEME_KEYS):
            raise ValueError(f"A theme holds only {', '.join(THEME_KEYS)}.")
        validate_definition({"schema": 2, "pages": [], **content})
        return content
    if not isinstance(content, dict) or set(content) != {"parts"}:
        raise ValueError("A shared part holds a list of parts.")
    d = validate_definition({"schema": 2, "pages": [{"title": "s", "parts": content["parts"]}]})
    if any(p["type"] == "snippet" for _, p in parts(d)):
        raise ValueError("A shared part cannot hold another shared part.")
    return {"parts": d["pages"][0]["parts"]}


def uses(d: dict, kind: str, key: str) -> int | None:
    """The revision of this item the definition uses, or None."""
    return next((r["revision"] for k, _, r in refs(d) if k == kind and r["key"] == key), None)


def _bump(d: dict, kind: str, key: str, revision: int) -> dict:
    d = copy.deepcopy(d)
    for k, _, ref in refs(d):
        if k == kind and ref["key"] == key:
            ref["revision"] = revision
    return d


def save(actor, kind: str, key: str, name: str, content) -> tuple[SharedItem, list[str]]:
    """A new revision of the item (made if new). Every template using an older revision moves
    to this one: its draft is updated and its live version is republished. Refused, with
    nothing changed, if that would point a template at fields its form lacks."""
    from .service import definition_issues

    if kind not in KINDS or not isinstance(key, str) or not KEY_RE.fullmatch(key):
        raise err("INVALID_SHARED", "A shared item needs a kind and a key (a-z, 0-9, _).")
    if not isinstance(name, str) or not name.strip():
        raise err("INVALID_SHARED", "A shared item needs a name.")
    try:
        content = check_content(kind, content)
    except ValueError as e:
        raise err("INVALID_SHARED", str(e)) from e
    updated: list[str] = []
    with transaction.atomic():
        item, _ = SharedItem.objects.select_for_update().get_or_create(
            kind=kind, key=key, defaults={"name": name.strip()})
        last = item.revisions.filter(revision=item.revision).first()
        if last is not None and last.content == content and item.name == name.strip():
            return item, updated
        item.revision += 1
        item.name = name.strip()
        item.save()
        SharedRevision.objects.create(item=item, revision=item.revision, content=content,
                                      created_by=actor)
        blocked = []
        for t in PdfTemplate.objects.select_related("form").order_by("form__key"):
            draft = t.versions.filter(status="draft").first()
            live = t.versions.filter(status="published").order_by("-number").first()
            moved = False
            if draft and uses(draft.definition, kind, key) not in (None, item.revision):
                draft.definition = _bump(draft.definition, kind, key, item.revision)
                draft.row_version += 1
                draft.save()
                moved = True
            if live and uses(live.definition, kind, key) not in (None, item.revision):
                new = _bump(live.definition, kind, key, item.revision)
                if issues := definition_issues(t, new):
                    blocked.append(f"{t.form.name}: {issues[0]['message']}")
                    continue
                number = live.number + 1 if draft is None else draft.number
                if draft is not None:                 # the draft stays the newest version
                    draft.number += 1
                    draft.save()
                PdfTemplateVersion.objects.create(template=t, number=number, definition=new,
                                                  status="published", published_at=timezone.now())
                moved = True
            if moved:
                updated.append(t.form.name)
        if blocked:                                     # raising rolls everything back
            raise err("SHARED_BLOCKED", "Some templates using this would show fields their form "
                      "does not have.", issues=blocked)
        audit.record(actor, f"pdf_{kind}.save", "pdf_shared", item.id,
                     f"Saved {kind} {key} v{item.revision}; updated: {', '.join(updated) or '-'}")
    return item, updated


def rename(actor, item: SharedItem, name) -> SharedItem:
    """Only the name people see; the key templates point at stays, so nothing else moves."""
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
        raise err("INVALID_SHARED", "A shared item needs a name (up to 100 characters).")
    old, item.name = item.name, name.strip()
    item.save(update_fields=["name"])
    audit.record(actor, f"pdf_{item.kind}.rename", "pdf_shared", item.id,
                 f"Renamed {item.kind} {item.key}: {old} -> {item.name}")
    return item


def delete(actor, item: SharedItem) -> None:
    """Only an item no template version uses, live, draft or old (an old version can still be
    shown or brought back), so no report ever points at a missing item."""
    users = sorted({v.template.form.name for v in PdfTemplateVersion.objects
                    .select_related("template__form")
                    if uses(v.definition, item.kind, item.key) is not None})
    if users:
        raise err("SHARED_IN_USE", f"Still used by {', '.join(users)}. Remove it from those "
                  "reports first.", 409)
    audit.record(actor, f"pdf_{item.kind}.delete", "pdf_shared", item.id,
                 f"Deleted {item.kind} {item.key} ({item.name})")
    item.delete()


def usage(item: SharedItem) -> list[dict]:
    """Templates using this item: their draft or live version, and which revision."""
    out = []
    for t in PdfTemplate.objects.select_related("form").order_by("form__key"):
        found = {v.status: uses(v.definition, item.kind, item.key)
                 for v in t.versions.order_by("number")}
        found = {k: r for k, r in found.items() if r is not None}
        if found:
            out.append({"template": t.id, "form": t.form.name, **found})
    return out
