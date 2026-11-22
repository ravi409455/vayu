"""Shared library: validation of definitions, linking/copying into drafts, accepting updates."""
from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models import Max

from apps.accounts import audit
from apps.core.errors import CodedError

from .access import validate_access
from .fieldtypes import ConfigError, validate_config
from .models import (
    KEY_RE,
    LIST_KEY_RE,
    Field,
    FieldType,
    LibraryItem,
    LibraryKind,
    Page,
    Section,
    ensure_draft,
)
from .rules import rule_syntax_issues

FIELD_KEYS = {"key", "label", "helper_text", "type", "config", "required", "required_if",
              "show_if", "visible", "access"}
CONTENT = ("label", "helper_text", "config")  # owned by the library once linked
OVERRIDES = ("required", "required_if", "show_if", "visible", "access")  # per-form, kept on update


def bad(code: str, message: str, status: int = 400) -> CodedError:
    return CodedError(code, message, status)


# ------------------------------------------------------------------ definitions

def validate_field_definition(d: Any, *, expect_key: str | None = None) -> dict:
    if not isinstance(d, dict) or set(d) - FIELD_KEYS or not {"key", "label", "type"} <= set(d):
        raise bad("INVALID_DEFINITION", "A field definition needs key, label and type, and only "
                  f"these properties: {', '.join(sorted(FIELD_KEYS))}.")
    if not KEY_RE.fullmatch(str(d["key"])):
        raise bad("INVALID_KEY", "Field keys are 2-63 chars: a-z, 0-9, _, starting with a letter.")
    if expect_key is not None and d["key"] != expect_key:
        raise bad("INVALID_DEFINITION", "The definition's key must equal the item's key.")
    if not isinstance(d["label"], str) or not d["label"].strip():
        raise bad("INVALID_DEFINITION", "A field needs a label.")
    if d["type"] not in FieldType.values:
        raise bad("INVALID_CONFIG", f"Unknown field type '{d['type']}'.")
    try:
        validate_config(d["type"], d.get("config", {}))
    except ConfigError as e:
        raise bad("INVALID_CONFIG", str(e)) from e
    rules = {"show_if": d.get("show_if"), "required_if": d.get("required_if")}
    if d["type"] == "derived":
        rules["config.rule"] = d["config"]["rule"]
    for name, rule in rules.items():
        issues = rule_syntax_issues(rule, name) if rule is not None else []
        if issues:
            raise bad("INVALID_RULE", "; ".join(f"{i.path}: {i.message}" for i in issues))
    try:
        validate_access(d.get("access", {}))
    except ValueError as e:
        raise bad("INVALID_ACCESS", str(e)) from e
    for flag in ("required", "visible"):
        if flag in d and not isinstance(d[flag], bool):
            raise bad("INVALID_DEFINITION", f"{flag} must be true or false.")
    if not isinstance(d.get("helper_text", ""), str):
        raise bad("INVALID_DEFINITION", "helper_text must be text.")
    return d


def validate_section_definition(d: Any) -> dict:
    if (not isinstance(d, dict) or set(d) - {"title", "show_if", "visible", "fields"}
            or not isinstance(d.get("fields"), list)):
        raise bad("INVALID_DEFINITION", "A section definition needs a title and a fields list.")
    if not isinstance(d.get("title"), str) or not d["title"].strip():
        raise bad("INVALID_DEFINITION", "A section needs a title.")
    if d.get("show_if") is not None:
        issues = rule_syntax_issues(d["show_if"], "show_if")
        if issues:
            raise bad("INVALID_RULE", "; ".join(f"{i.path}: {i.message}" for i in issues))
    keys = []
    for f in d["fields"]:
        validate_field_definition(f)
        keys.append(f["key"])
    if len(set(keys)) != len(keys):
        raise bad("INVALID_DEFINITION", "Field keys must be unique within the section.")
    return d


def _check_immutable(kind: str, old: dict, new: dict) -> None:
    if kind == LibraryKind.FIELD:
        if new.get("type") != old["type"]:  # the key was already checked in update_item
            raise bad("TYPE_IMMUTABLE", "A library field's type can never change.")
    else:
        old_types = {f["key"]: f["type"] for f in old["fields"]}
        for f in new["fields"]:
            if f["key"] in old_types and old_types[f["key"]] != f["type"]:
                raise bad("TYPE_IMMUTABLE", f"Field '{f['key']}' cannot change type.")


# ------------------------------------------------------------------ items

def create_item(actor, *, kind: str, key: str, name: str | None, definition: Any) -> LibraryItem:
    if kind == LibraryKind.FIELD:
        validate_field_definition(definition, expect_key=key)
    elif kind == LibraryKind.SECTION:
        if not LIST_KEY_RE.fullmatch(key or ""):
            raise bad("INVALID_KEY", "Use lowercase letters, digits and _; start with a letter.")
        validate_section_definition(definition)
    else:
        raise bad("INVALID_DEFINITION", "kind must be 'field' or 'section'.")
    if LibraryItem.objects.filter(kind=kind, key=key).exists():
        raise bad("DUPLICATE_KEY", f"A library {kind} with key '{key}' already exists.")
    default_name = definition["label"] if kind == LibraryKind.FIELD else definition["title"]
    item = LibraryItem.objects.create(kind=kind, key=key, name=name or default_name,
                                      definition=definition)
    audit.record(actor, "library.create", "library_item", item.id, f"{kind} {key}")
    return item


@transaction.atomic
def update_item(actor, item: LibraryItem, *, definition: Any = None, archived: bool | None = None,
                name: str | None = None) -> LibraryItem:
    if definition is not None:
        if item.kind == LibraryKind.FIELD:
            if isinstance(definition, dict) and definition.get("key", item.key) != item.key:
                raise bad("KEY_IMMUTABLE", "A library field's key can never change.")
            validate_field_definition(definition, expect_key=item.key)
        else:
            validate_section_definition(definition)
        _check_immutable(item.kind, item.definition, definition)
        if definition != item.definition:
            item.definition = definition
            item.revision += 1
            audit.record(actor, "library.update", "library_item", item.id,
                         f"{item.kind} {item.key} -> revision {item.revision}")
    if name is not None:
        item.name = name
    if archived is not None and archived != item.archived:
        item.archived = archived
        audit.record(actor, "library.archive" if archived else "library.unarchive",
                     "library_item", item.id, f"{item.kind} {item.key}")
    item.save()
    return item


def usages(item: LibraryItem) -> list[dict]:
    rows = set()
    for model in (Field, Section):
        rows |= set(model.objects.filter(library_item=item).values_list(
            "version__form__key", "version__number", "version__status"))
    return [{"form": f, "version": n, "status": s} for f, n, s in sorted(rows)]


def delete_item(actor, item: LibraryItem) -> None:
    if usages(item):
        raise CodedError("IN_USE", "This item is used by a form; archive it instead.", 409)
    audit.record(actor, "library.delete", "library_item", item.id, f"{item.kind} {item.key}")
    item.delete()


# ------------------------------------------------------------------ into forms

def _field_attrs(d: dict) -> dict:
    return {"label": d["label"], "helper_text": d.get("helper_text", ""), "type": d["type"],
            "config": d.get("config", {}), "required": d.get("required", False),
            "required_if": d.get("required_if"), "show_if": d.get("show_if"),
            "visible": d.get("visible", True), "access": d.get("access", {})}


def _usable(item: LibraryItem, kind: str) -> None:
    if item.kind != kind:
        raise bad("WRONG_KIND", f"Expected a {kind} item.")
    if item.archived:
        raise CodedError("ARCHIVED", "This library item is archived.", 409)


def _next_order(qs) -> int:
    return (qs.aggregate(m=Max("order"))["m"] or 0) + 1


def locked(obj: Field | Section) -> bool:
    if isinstance(obj, Section):
        return obj.library_item_id is not None
    return obj.library_item_id is not None or obj.section.library_item_id is not None


def ensure_not_locked(section: Section) -> None:
    if section.library_item_id is not None:
        raise CodedError("LINKED_LOCKED", "This section is linked to the library; unlink it to "
                         "change its structure.", 409)


@transaction.atomic
def add_field(actor, section: Section, item: LibraryItem, link: bool) -> Field:
    _usable(item, LibraryKind.FIELD)
    ensure_draft(section.version_id)
    ensure_not_locked(section)
    field = Field(version_id=section.version_id, section=section, key=item.definition["key"],
                  order=_next_order(section.fields.all()), **_field_attrs(item.definition))
    if link:
        field.library_item, field.library_revision = item, item.revision
    field.save()
    audit.record(actor, "form.link_library" if link else "form.copy_library", "field", field.id,
                 f"{field.key} from library {item.key} r{item.revision}")
    return field


def _build_section_fields(section: Section, definition: dict, start: int = 0) -> None:
    for i, fd in enumerate(definition["fields"], start=start):
        Field(version_id=section.version_id, section=section, key=fd["key"], order=i,
              **_field_attrs(fd)).save()


@transaction.atomic
def add_section(actor, page: Page, item: LibraryItem, link: bool) -> Section:
    _usable(item, LibraryKind.SECTION)
    ensure_draft(page.version_id)
    d = item.definition
    section = Section(version_id=page.version_id, page=page, title=d["title"],
                      order=_next_order(page.sections.all()), visible=d.get("visible", True),
                      show_if=d.get("show_if"))
    if link:
        section.library_item, section.library_revision = item, item.revision
    section.save()
    _build_section_fields(section, d)
    audit.record(actor, "form.link_library" if link else "form.copy_library", "section",
                 section.id, f"{section.title} from library {item.key} r{item.revision}")
    return section


@transaction.atomic
def accept_update(actor, obj: Field | Section) -> Field | Section:
    ensure_draft(obj.version_id)
    item = obj.library_item
    if item is None:
        raise bad("NOT_LINKED", "This item is not linked to the library.")
    if obj.library_revision == item.revision:
        return obj
    d = item.definition
    if isinstance(obj, Field):
        for attr in CONTENT:
            setattr(obj, attr, _field_attrs(d)[attr])
        obj.library_revision = item.revision
        obj.save()
    else:
        obj.title, obj.library_revision = d["title"], item.revision
        obj.save()
        existing = {f.key: f for f in obj.fields.all()}
        wanted = {fd["key"]: fd for fd in d["fields"]}
        for key, f in existing.items():
            if key not in wanted:
                f.delete()
        for fd in d["fields"]:
            if fd["key"] in existing:
                f = existing[fd["key"]]
                for attr in CONTENT:
                    setattr(f, attr, _field_attrs(fd)[attr])
                f.save()
        new = [fd for fd in d["fields"] if fd["key"] not in existing]
        _build_section_fields(obj, {"fields": new}, start=_next_order(obj.fields.all()))
    audit.record(actor, "form.accept_library_update", "field" if isinstance(obj, Field)
                 else "section", obj.id, f"{item.key} -> r{item.revision}")
    return obj


def unlink(actor, obj: Field | Section) -> Field | Section:
    ensure_draft(obj.version_id)
    if isinstance(obj, Field) and obj.section.library_item_id is not None:
        raise bad("VIA_SECTION", "This field is part of a linked section; unlink the section.")
    if obj.library_item is None:
        raise bad("NOT_LINKED", "This item is not linked to the library.")
    key = obj.library_item.key
    obj.library_item, obj.library_revision = None, None
    obj.save()
    audit.record(actor, "form.unlink_library", "field" if isinstance(obj, Field) else "section",
                 obj.id, f"unlinked from {key}")
    return obj


@transaction.atomic
def save_to_library(actor, obj: Field | Section, *, key: str | None, name: str | None):
    ensure_draft(obj.version_id)
    if locked(obj):
        raise CodedError("ALREADY_LINKED", "This item is already linked to the library.", 409)
    if isinstance(obj, Field):
        if obj.is_system:
            raise CodedError("SYSTEM_FIELD", "System fields cannot go to the library.", 400)
        definition: dict[str, Any] = {"key": obj.key, "label": obj.label, "type": obj.type,
                                      "helper_text": obj.helper_text, "config": obj.config,
                                      "required": obj.required, "required_if": obj.required_if,
                                      "show_if": obj.show_if, "visible": obj.visible,
                                      "access": obj.access}
        item = create_item(actor, kind=LibraryKind.FIELD, key=key or obj.key, name=name,
                           definition=definition)
    else:
        fields = list(obj.fields.all())
        if any(f.is_system for f in fields):
            raise CodedError("SYSTEM_FIELD", "This section holds system fields.", 400)
        definition = {"title": obj.title, "visible": obj.visible, "show_if": obj.show_if,
                      "fields": [{"key": f.key, "label": f.label, "type": f.type,
                                  "helper_text": f.helper_text, "config": f.config,
                                  "required": f.required, "required_if": f.required_if,
                                  "show_if": f.show_if, "visible": f.visible,
                                  "access": f.access} for f in fields]}
        item = create_item(actor, kind=LibraryKind.SECTION, key=key or "", name=name,
                           definition=definition)
    obj.library_item, obj.library_revision = item, item.revision
    obj.save()
    audit.record(actor, "form.link_library", "field" if isinstance(obj, Field) else "section",
                 obj.id, f"saved to library as {item.key}")
    return item
