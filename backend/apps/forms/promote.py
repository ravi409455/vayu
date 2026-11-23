"""Promotion: one form version (with the library items, master lists and PDF template it depends
on) leaves one environment as a JSON bundle and enters another as a DRAFT. Nothing is published
by an import, and nothing is written if anything conflicts. No ids travel: everything is matched
by key."""
from typing import Any

from django.db import transaction
from django.db.models import Max

from apps.accounts import audit
from apps.core.errors import CodedError

from .access import validate_access
from .fieldtypes import validate_config as validate_field_config
from .models import (
    KEY_RE,
    Field,
    FieldKey,
    FieldType,
    Form,
    FormAsset,
    FormKind,
    FormVersion,
    LibraryItem,
    MasterList,
    MasterListItem,
    Page,
    Section,
    VersionCheck,
    VersionStatus,
)
from .rules import rule_syntax_issues
from .system_fields import SYSTEM_FIELDS

SCHEMA = 1


def bad(code: str, message: str, status: int = 400, **extra) -> CodedError:
    return CodedError(code, message, status, **extra)


# ------------------------------------------------------------------ export

def _field(f: Field) -> dict:
    link = f.library_item
    return {"key": f.key, "label": f.label, "helper_text": f.helper_text, "type": f.type,
            "config": f.config, "required": f.required, "required_if": f.required_if,
            "show_if": f.show_if, "visible": f.visible, "order": f.order, "access": f.access,
            "is_system": f.is_system,
            "library": {"key": link.key, "revision": f.library_revision} if link else None}


def _lists_in(definition: dict) -> set[str]:
    """Master list keys used by fields inside a library definition."""
    fields = definition.get("fields", [definition])
    return {f["config"]["list"] for f in fields
            if f.get("type") == "master_list" and f.get("config", {}).get("list")}


def export_bundle(version: FormVersion) -> dict:
    from apps.reports.models import PdfTemplate

    pages, items, lists = [], {}, set()
    for page in Page.objects.filter(version=version):
        sections = []
        for s in Section.objects.filter(page=page).select_related("library_item"):
            fields = list(Field.objects.filter(section=s).select_related("library_item"))
            for f in fields:
                if f.library_item:
                    items[(f.library_item.kind, f.library_item.key)] = f.library_item
                if f.type == "master_list":
                    lists.add(f.config.get("list", ""))
            if s.library_item:
                items[(s.library_item.kind, s.library_item.key)] = s.library_item
            link = s.library_item
            sections.append({
                "title": s.title, "order": s.order, "visible": s.visible, "show_if": s.show_if,
                "access": s.access,
                "library": {"key": link.key, "revision": s.library_revision} if link else None,
                "fields": [_field(f) for f in fields]})
        pages.append({"title": page.title, "order": page.order, "visible": page.visible,
                      "gate": page.gate, "slot": page.slot, "show_if": page.show_if,
                      "access": page.access, "sections": sections})
    library = [{"kind": i.kind, "key": i.key, "name": i.name, "definition": i.definition,
                "revision": i.revision, "archived": i.archived}
               for _, i in sorted(items.items())]
    for i in library:
        lists |= _lists_in(i["definition"])
    master_lists = [{"key": m.key, "name": m.name,
                     "items": [{"key": it.key, "label": it.label, "order": it.order,
                                "archived": it.archived} for it in m.items.all()]}
                    for m in MasterList.objects.filter(key__in=lists).order_by("key")]
    template = PdfTemplate.objects.filter(form=version.form).first()
    last = template.versions.order_by("-number").first() if template else None
    return {
        "schema": SCHEMA,
        "form": {"key": version.form.key, "kind": version.form.kind, "name": version.form.name,
                 "inspection_type": version.form.inspection_type,
                 "submission_roles": version.form.submission_roles},
        "version": {"rating_config": version.rating_config, "pages": pages,
                    "checks": [{"rule": c.rule, "message": c.message, "fields": c.fields,
                                "order": c.order}
                               for c in VersionCheck.objects.filter(version=version)]},
        "library": library, "master_lists": master_lists,
        "pdf_template": {"definition": last.definition} if last else None,
        "assets": _export_assets(pages, library),
    }


def _image_ids(pages: list, library: list) -> set[str]:
    """Picture ids used by image fields (in the form itself and in library definitions)."""
    out = {f["config"].get("asset") for p in pages for s in p["sections"] for f in s["fields"]
           if f["type"] == "image"}
    for item in library:
        d = item["definition"]
        out |= {f["config"].get("asset") for f in d.get("fields", [d]) if f.get("type") == "image"}
    return {i for i in out if i}


def _export_assets(pages: list, library: list) -> dict:
    from . import assets

    ids = _image_ids(pages, library)
    return {str(a.id): assets.export(a) for a in FormAsset.objects.filter(pk__in=ids)}


def _remap_assets(b: dict, mapping: dict[str, str]) -> None:
    """Point every image field at the picture's new id on this server."""
    def fix(f):
        if f.get("type") == "image" and f.get("config", {}).get("asset") in mapping:
            f["config"]["asset"] = mapping[f["config"]["asset"]]

    for p in b["version"]["pages"]:
        for s in p["sections"]:
            for f in s["fields"]:
                fix(f)
    for item in b["library"]:
        d = item["definition"]
        for f in d.get("fields", [d]):
            fix(f)


def _import_assets(actor, b: dict) -> dict[str, str]:
    from . import assets

    payload = b.get("assets") or {}
    if not isinstance(payload, dict):
        raise bad("INVALID_BUNDLE", "The bundle's pictures are not valid.")
    return {old: str(assets.import_from_bundle(actor, p).id) for old, p in payload.items()}


# ------------------------------------------------------------------ import

def _check_shape(b: Any) -> None:
    if not isinstance(b, dict):
        raise bad("INVALID_BUNDLE", "The bundle must be a JSON object.")
    if isinstance(b.get("schema"), int) and b["schema"] > SCHEMA:
        raise bad("BUNDLE_TOO_NEW", "This bundle comes from a newer version of Vayu; upgrade "
                  "this server first.")
    form, version = b.get("form"), b.get("version")
    if (b.get("schema") != SCHEMA or not isinstance(form, dict) or not isinstance(version, dict)
            or not isinstance(version.get("pages"), list)
            or not isinstance(b.get("library"), list) or not isinstance(b.get("master_lists"), list)
            or form.get("kind") not in FormKind.values
            or not all(isinstance(form.get(k), str) and form[k] or k == "inspection_type"
                       for k in ("key", "name"))):
        raise bad("INVALID_BUNDLE", "This is not a valid Vayu form bundle.")
    known = {(i.get("kind"), i.get("key")) for i in b["library"] if isinstance(i, dict)}
    for p in version["pages"]:
        for s in p.get("sections", []):
            links = [s.get("library")] + [f.get("library") for f in s.get("fields", [])]
            for link in links:
                kind = "section" if link is s.get("library") else "field"
                if link and (kind, link.get("key")) not in known:
                    raise bad("INVALID_BUNDLE", f"Library item '{link.get('key')}' is missing "
                              "from the bundle.")


def _check_content(b: dict) -> None:
    """Same checks as the normal editing paths: a bundle is not a way around them."""
    from apps.reports.definition import validate_definition
    from apps.scoring.engine import validate_config as validate_rating

    def rules(*pairs):
        for name, rule in pairs:
            if rule_syntax_issues(rule, name):
                raise ValueError(f"{name} is not a valid rule.")

    def field(f):
        if f["type"] not in FieldType.values or not KEY_RE.fullmatch(f["key"]):
            raise ValueError(f"Field '{f['key']}' has an invalid key or type.")
        validate_field_config(f["type"], f["config"])
        validate_access(f["access"])
        rules(("show_if", f["show_if"]), ("required_if", f["required_if"]))

    try:
        if not KEY_RE.fullmatch(b["form"]["key"]):
            raise ValueError("Invalid form key.")
        validate_rating(b["version"].get("rating_config", {}))
        roles = b["form"].get("submission_roles", ["expert", "ops"])
        if not isinstance(roles, list) or set(roles) - {"expert", "ops"}:
            raise ValueError("submission_roles may only name expert and ops.")
        for p in b["version"]["pages"]:
            if not isinstance(p.get("gate", False), bool):
                raise ValueError("A page's gate must be true or false.")
            if p.get("slot", "") not in ("", "before", "after"):
                raise ValueError("A page's slot must be before or after.")
            validate_access(p["access"])
            rules(("page.show_if", p["show_if"]))
            for s in p["sections"]:
                validate_access(s["access"])
                rules(("section.show_if", s["show_if"]))
                for f in s["fields"]:
                    field(f)
        for c in b["version"].get("checks", []):
            rules(("check.rule", c["rule"]))
        for it in b["library"]:
            if it["kind"] == "field":
                field({"key": "lib_field", "access": {}, "show_if": None, "required_if": None,
                       "config": {}, **it["definition"]})
        if b.get("pdf_template"):
            validate_definition(b["pdf_template"]["definition"])
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        raise bad("INVALID_BUNDLE", f"The bundle's content is not valid: {e}") from e


def _conflicts(b: dict, existing: Form | None) -> list[str]:
    out: list[str] = []
    form = b["form"]
    if existing and existing.kind != form["kind"]:
        out.append(f"Form '{form['key']}' exists with kind {existing.kind}; the bundle's kind is "
                   f"{form['kind']}.")
    if form["inspection_type"]:
        clash = Form.objects.filter(kind=FormKind.INSPECTION, is_active=True,
                                    inspection_type=form["inspection_type"])
        if existing:
            clash = clash.exclude(pk=existing.pk)
        other = clash.first()
        if form["kind"] == FormKind.INSPECTION and other is not None:
            out.append(f"The inspection type '{form['inspection_type']}' is already handled by "
                       f"form '{other.key}'.")
    if form["kind"] in (FormKind.BOOKING, FormKind.OPS) and not existing:
        if Form.objects.filter(kind=form["kind"], is_active=True).exists():
            out.append(f"There is already an active {form['kind']} form.")
    if existing:
        reserved = dict(FieldKey.objects.filter(form=existing).values_list("key", "type"))
        for p in b["version"]["pages"]:
            for s in p["sections"]:
                for f in s["fields"]:
                    if reserved.get(f["key"], f["type"]) != f["type"]:
                        out.append(f"Field '{f['key']}' was used before as {reserved[f['key']]}; "
                                   f"the bundle has {f['type']}.")
    for it in b["library"]:
        have = LibraryItem.objects.filter(kind=it["kind"], key=it["key"]).first()
        if have and it["kind"] == "field" and have.definition.get("type") != \
                it["definition"].get("type"):
            out.append(f"Library field '{it['key']}' exists with type "
                       f"{have.definition.get('type')}; the bundle has "
                       f"{it['definition'].get('type')}.")
    return out


def _import_lists(b: dict, notes: list[str]) -> int:
    created = 0
    for m in b["master_lists"]:
        ml, _ = MasterList.objects.get_or_create(key=m["key"], defaults={"name": m["name"]})
        for it in m["items"]:
            item, made = MasterListItem.objects.get_or_create(
                list=ml, key=it["key"], defaults={"label": it["label"], "order": it["order"],
                                                  "archived": it["archived"]})
            created += made
            if not made and item.label != it["label"]:
                notes.append(f"List {m['key']}/{it['key']}: kept label '{item.label}' "
                             f"(bundle has '{it['label']}').")
    return created


def _import_library(b: dict, notes: list[str]) -> tuple[dict, int]:
    items, created = {}, 0
    for it in b["library"]:
        obj = LibraryItem.objects.filter(kind=it["kind"], key=it["key"]).first()
        if obj is None:
            obj = LibraryItem.objects.create(kind=it["kind"], key=it["key"], name=it["name"],
                                             definition=it["definition"], revision=it["revision"],
                                             archived=it["archived"])
            created += 1
        elif obj.definition != it["definition"]:
            notes.append(f"Library {it['kind']} '{it['key']}' already exists here with different "
                         f"content (revision {obj.revision} vs the bundle's {it['revision']}); "
                         "kept it. Accept updates in the draft if you want the newer one.")
        items[(it["kind"], it["key"])] = obj
    return items, created


def _is_system(version, f: dict) -> bool:
    """Only the platform's own fields are system fields; a bundle cannot grant that flag."""
    return any(f["key"] == spec["key"] for spec in SYSTEM_FIELDS[version.form.kind])


def _build_field(version, section, f: dict, items: dict) -> None:
    link = f.get("library")
    Field(version=version, section=section, key=f["key"], label=f["label"],
          helper_text=f["helper_text"], type=f["type"], config=f["config"],
          required=f["required"], required_if=f["required_if"], show_if=f["show_if"],
          visible=f["visible"], order=f["order"], access=f["access"],
          is_system=_is_system(version, f),
          library_item=items[("field", link["key"])] if link else None,
          library_revision=link["revision"] if link else None).save()


def import_bundle(actor, b: Any) -> dict:
    _check_shape(b)
    from apps.reports.models import PdfTemplate, PdfTemplateVersion

    form_data = b["form"]
    existing = Form.objects.filter(key=form_data["key"]).first()
    conflicts = _conflicts(b, existing)
    if conflicts:
        raise bad("IMPORT_CONFLICTS", "This bundle conflicts with what is already here.",
                  conflicts=conflicts)
    if existing and existing.versions.filter(status=VersionStatus.DRAFT).exists():
        raise bad("DRAFT_EXISTS", "This form already has a draft; publish or discard it first.",
                  409)
    template = PdfTemplate.objects.filter(form=existing).first() if existing else None
    if template and template.versions.filter(status="draft").exists() and b.get("pdf_template"):
        raise bad("DRAFT_EXISTS", "This form's PDF template already has a draft.", 409)
    notes: list[str] = []
    with transaction.atomic():
        _remap_assets(b, _import_assets(actor, b))
        list_items = _import_lists(b, notes)
        items, library_created = _import_library(b, notes)
        _check_content(b)       # needs the lists; failure rolls all back
        form = existing or Form.objects.create(
            key=form_data["key"], kind=form_data["kind"], name=form_data["name"],
            inspection_type=form_data["inspection_type"],
            submission_roles=form_data.get("submission_roles", ["expert", "ops"]))
        number = (form.versions.aggregate(n=Max("number"))["n"] or 0) + 1
        version = FormVersion.objects.create(form=form, number=number,
                                             rating_config=b["version"].get("rating_config", {}))
        for p in b["version"]["pages"]:
            page = Page.objects.create(version=version, title=p["title"], order=p["order"],
                                       visible=p["visible"], gate=p.get("gate", False),
                                       slot=p.get("slot", ""), show_if=p["show_if"],
                                       access=p["access"])
            for s in p["sections"]:
                link = s.get("library")
                section = Section.objects.create(
                    version=version, page=page, title=s["title"], order=s["order"],
                    visible=s["visible"], show_if=s["show_if"], access=s["access"],
                    library_item=items[("section", link["key"])] if link else None,
                    library_revision=link["revision"] if link else None)
                for f in s["fields"]:
                    _build_field(version, section, f, items)
        for c in b["version"].get("checks", []):
            VersionCheck.objects.create(version=version, rule=c["rule"], message=c["message"],
                                        fields=c["fields"], order=c["order"])
        if b.get("pdf_template") and form.kind == FormKind.INSPECTION:
            t, _ = PdfTemplate.objects.get_or_create(form=form)
            last = t.versions.order_by("-number").first()
            PdfTemplateVersion.objects.create(template=t, number=(last.number + 1) if last else 1,
                                              definition=b["pdf_template"]["definition"])
        audit.record(actor, "form.promote_import", "form", form.id,
                     f"Imported {form.key} as draft v{number}")
    return {"form": form.id, "draft_version": version.id,
            "created": {"form": existing is None, "master_list_items": list_items,
                        "library_items": library_created},
            "notes": notes}
