"""Puts a converted spec (apps/core/setup/clappia.py) into a form: builds a draft, publishes it.
Running it again with the same spec changes nothing; a different spec publishes a new version
(inspections already started keep theirs)."""
import json
from typing import Any

from django.db import transaction

from apps.forms import services as form_services
from apps.forms.models import Field, Form, FormVersion, Page, Section, VersionStatus

FIELD_ATTRS = ("key", "label", "type", "config", "required", "show_if", "helper_text")


def _spec_rows(spec: dict, extra: dict) -> list:
    rows: list[tuple] = []
    for p in spec["pages"]:
        for s in p["sections"]:
            rows.append(("section", p["title"], s["title"], s.get("show_if")))
            for f in s["fields"]:
                rows.append(("field",) + tuple(json.dumps(f.get(a), sort_keys=True)
                                               for a in FIELD_ATTRS))
    return rows + [("extra", json.dumps(extra, sort_keys=True))]


def _version_rows(v: FormVersion, extra_keys: tuple[str, ...]) -> list:
    rows: list[tuple] = []
    for p in Page.objects.filter(version=v).order_by("order", "id"):
        for s in Section.objects.filter(page=p).order_by("order", "id"):
            rows.append(("section", p.title, s.title, s.show_if))
            for f in s.fields.order_by("order", "id"):
                rows.append(("field",) + tuple(json.dumps(getattr(f, a) or None if a in (
                    "show_if", "helper_text") else getattr(f, a), sort_keys=True)
                    for a in FIELD_ATTRS))
    extra = {k: getattr(v, k) for k in extra_keys}
    return rows + [("extra", json.dumps(extra, sort_keys=True))]


def _norm(spec: dict) -> dict:
    """The spec as it will be stored (system fields keep their own type, config and rules)."""
    out = json.loads(json.dumps(spec))
    for p in out["pages"]:
        for s in p["sections"]:
            for f in s["fields"]:
                f.setdefault("show_if", None)
                f["helper_text"] = f.get("helper_text") or None
    return out


@transaction.atomic
def apply(admin, form: Form, spec: dict, extra: dict | None = None) -> str:
    """Make `form`'s live version match `spec` ("unchanged" | "published v<n>"). `extra`:
    version settings such as key_checks and rating_config. A spec field whose key is a system
    field of the form takes that field's place (relabelled, moved), keeping its locked type."""
    extra = extra or {}
    spec = _norm(spec)
    live = form.versions.filter(status=VersionStatus.PUBLISHED).order_by("-number").first()
    system = {f.key: f for f in Field.objects.filter(version=live, is_system=True)} if live \
        else {}
    if live is not None:
        want = _spec_rows(_with_system(spec, system), extra)
        if want == _version_rows(live, tuple(extra)):
            return "unchanged"
    draft = form.versions.filter(status=VersionStatus.DRAFT).first()
    if draft is None:
        draft = form_services.create_draft(admin, form) if live else form.versions.get()
    _fill(draft, spec)
    for k, val in extra.items():
        setattr(draft, k, val)
    draft.save()
    draft.refresh_from_db()
    v = form_services.publish_version(admin, draft.id, draft.row_version)
    return f"published v{v.number}"


def _with_system(spec: dict, system: dict[str, Field]) -> dict:
    """What a system field looks like once placed: its own type/config/rules, the spec's label.
    One the spec does not place sits at the end of the first section (as _fill puts it)."""
    out = json.loads(json.dumps(spec))
    placed = {f["key"] for p in out["pages"] for s in p["sections"] for f in s["fields"]}
    first = out["pages"][0]["sections"][0]["fields"] if out["pages"] else []
    for key in sorted(set(system) - placed):
        sf = system[key]
        first.append({"key": key, "label": sf.label, "config": sf.config})
    for p in out["pages"]:
        for s in p["sections"]:
            for f in s["fields"]:
                found = system.get(f["key"])
                if found is not None:
                    cfg = found.config
                    if f["config"].get("options") and found.config.get("options") is not None:
                        cfg = {**found.config, "options": f["config"]["options"]}
                    f.update(type=found.type, config=cfg, required=found.required,
                             show_if=found.show_if, helper_text=found.helper_text or None)
    return out


def _fill(v: FormVersion, spec: dict) -> None:
    system = {f.key: f for f in Field.objects.filter(version=v, is_system=True)}
    Field.objects.filter(version=v, is_system=False).delete()
    old_sections = list(Section.objects.filter(version=v))
    old_pages = list(Page.objects.filter(version=v))
    placed: set[str] = set()
    for pn, p in enumerate(spec["pages"]):
        page = Page.objects.create(version=v, title=p["title"], order=1000 + pn,
                                   gate=p.get("gate", False))
        for sn, s in enumerate(p["sections"]):
            sec = Section.objects.create(version=v, page=page, title=s["title"], order=sn,
                                         show_if=s.get("show_if"))
            for fn, f in enumerate(s["fields"]):
                sf = system.get(f["key"])
                if sf is not None:
                    keep = {"section": sec, "order": fn, "label": f["label"]}
                    if f["config"].get("options") and sf.config.get("options") is not None:
                        keep["config"] = {**sf.config, "options": f["config"]["options"]}
                    Field.objects.filter(pk=sf.pk).update(**keep)
                    placed.add(sf.key)
                    continue
                Field.objects.create(version=v, section=sec, order=fn, key=f["key"],
                                     label=f["label"], type=f["type"], config=f["config"],
                                     required=f["required"], show_if=f.get("show_if"),
                                     helper_text=f.get("helper_text") or "")
    missing = set(system) - placed
    if missing:      # a system field the spec does not place: keep it on the first page
        first = Section.objects.filter(version=v, page__order=1000).order_by("order").first()
        for n, key in enumerate(sorted(missing)):
            Field.objects.filter(pk=system[key].pk).update(section=first, order=900 + n)
    for s in old_sections:
        s.delete()
    for p in old_pages:
        p.delete()
    for n, page in enumerate(Page.objects.filter(version=v).order_by("order", "id")):
        Page.objects.filter(pk=page.pk).update(order=n)


def ensure_form(admin, *, key: str, name: str, itype: str) -> Form:
    form = Form.objects.filter(key=key).first()
    return form or form_services.create_form(admin, key=key, name=name, inspection_type=itype)


def system_form(ftype: str) -> Form:
    form_services.ensure_system_forms()
    return Form.objects.get(type=ftype)


def describe(spec: dict) -> dict[str, Any]:
    fields = [f for p in spec["pages"] for s in p["sections"] for f in s["fields"]]
    return {"pages": len(spec["pages"]), "fields": len(fields)}
