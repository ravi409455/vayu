"""Push a library item's newest revision to every form that uses it, all or nothing.

The preview runs the very same steps as the push and then rolls everything back, so what it lists
(forms, every setting that will change, every problem) is exactly what the push would do."""
from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.accounts import audit
from apps.core.concurrency import check_row_version
from apps.core.errors import CodedError
from apps.integrations.values import publish_warnings

from . import library, services
from .models import Field, Form, FormVersion, LibraryItem, LibraryKind, Section, VersionStatus
from .rules import validate_version

FIELD_SETTINGS = ("label", "helper_text", "config", "required", "required_if", "show_if",
                  "visible", "access")
SECTION_SETTINGS = ("title", "visible", "show_if", "access")


class _DryRun(Exception):
    def __init__(self, result: dict[str, Any]):
        self.result = result


def _usages(version: FormVersion, item: LibraryItem) -> list[Field | Section]:
    model = Field if item.kind == LibraryKind.FIELD else Section
    return list(model.objects.filter(version=version, library_item=item).order_by("id"))


def affected(item: LibraryItem) -> list[tuple[Form, FormVersion]]:
    """Forms whose newest version links this item at an older revision, in id order."""
    model = Field if item.kind == LibraryKind.FIELD else Section
    form_ids = set(model.objects.filter(library_item=item).values_list("version__form_id",
                                                                       flat=True))
    out = []
    for form in Form.objects.filter(pk__in=form_ids).order_by("id"):
        latest = form.versions.order_by("-number").first()
        assert latest is not None  # noqa: S101 - invariant, narrows the type
        if any(o.library_revision != item.revision for o in _usages(latest, item)):
            out.append((form, latest))
    return out


def _diff_settings(target: str, obj: Any, wanted: dict[str, Any],
                   names: tuple[str, ...]) -> list[dict[str, Any]]:
    return [{"target": target, "setting": n, "from": getattr(obj, n), "to": wanted[n]}
            for n in names if getattr(obj, n) != wanted[n]]


def _wanted_field(d: dict[str, Any]) -> dict[str, Any]:
    return {"label": d["label"], "helper_text": d.get("helper_text", ""),
            "config": d.get("config", {}), "required": d.get("required", False),
            "required_if": d.get("required_if"), "show_if": d.get("show_if"),
            "visible": d.get("visible", True), "access": d.get("access", {})}


def _changes(obj: Field | Section, item: LibraryItem) -> list[dict[str, Any]]:
    """Every setting that accepting the update would change on this linked field / section."""
    d = item.definition
    if isinstance(obj, Field):
        return _diff_settings(obj.key, obj, _wanted_field(d), FIELD_SETTINGS)
    wanted = {"title": d["title"], "visible": d.get("visible", True),
              "show_if": d.get("show_if"), "access": d.get("access", {})}
    out = _diff_settings(f"section {obj.title}", obj, wanted, SECTION_SETTINGS)
    have = {f.key: f for f in obj.fields.all()}
    keys = [fd["key"] for fd in d["fields"]]
    out += [{"target": k, "setting": "removed", "from": True, "to": False}
            for k in have if k not in keys]
    for i, fd in enumerate(d["fields"]):
        if fd["key"] not in have:
            out.append({"target": fd["key"], "setting": "added", "from": False, "to": True})
            continue
        f = have[fd["key"]]
        out += _diff_settings(fd["key"], f, _wanted_field(fd), FIELD_SETTINGS)
        if f.order != i:
            out.append({"target": fd["key"], "setting": "order", "from": f.order, "to": i})
    return out


def _problems(form: Form, draft: FormVersion) -> list[dict[str, Any]]:
    from apps.reports.service import latest_layout_issues

    issues = [i.__dict__ for i in validate_version(draft) + services.system_field_issues(draft)]
    issues += latest_layout_issues(form)
    return [{"form": form.key, "path": i["path"], "code": i["code"], "message": i["message"]}
            for i in issues]


def _run(actor: Any, item: LibraryItem, *, publish: bool, commit: bool) -> dict[str, Any]:
    """Do the push inside a transaction. Returns the report; commits only when `commit` and
    nothing is wrong."""
    result: dict[str, Any] = {"forms": [], "skipped": [], "blocked": False}
    with transaction.atomic():
        pairs = affected(item)
        ids = [f.id for f, _ in pairs]
        list(Form.objects.select_for_update().filter(pk__in=ids).order_by("id"))   # fixed order
        drafts: list[tuple[Form, FormVersion]] = []
        for form, latest in pairs:
            if not form.is_active:
                result["skipped"].append({"form": form.key, "reason": "inactive"})
                continue
            state = "draft" if latest.status == VersionStatus.DRAFT else "published_only"
            changes = [c for o in _usages(latest, item) if o.library_revision != item.revision
                       for c in _changes(o, item)]
            draft = latest if state == "draft" else services.create_draft(actor, form)
            for obj in _usages(draft, item):
                library.accept_update(actor, obj)
            problems = _problems(form, draft)
            result["forms"].append({"form": form.key, "type": form.type, "state": state,
                                    "changes": changes, "problems": problems,
                                    "warnings": publish_warnings(draft, published=False)})
            drafts.append((form, draft))
        result["blocked"] = any(f["problems"] for f in result["forms"])
        if result["blocked"] or not commit:
            raise _DryRun(result)
        if publish:
            for _form, draft in drafts:
                services.publish_version(actor, draft.id, FormVersion.objects.get(
                    pk=draft.id).row_version)
        audit.record(actor, "library.push", "library_item", item.id,
                     f"{item.kind} {item.key} r{item.revision} -> "
                     f"{', '.join(f['form'] for f in result['forms']) or 'no forms'}"
                     f"{' (published)' if publish else ''}")
    return result


def preview(actor: Any, item: LibraryItem) -> dict[str, Any]:
    try:
        return _run(actor, item, publish=False, commit=False)
    except _DryRun as e:
        return e.result


def push(actor: Any, item: LibraryItem, *, revision: Any, publish: bool,
         confirm: bool) -> dict[str, Any]:
    check_row_version(item, revision, "STALE_LIBRARY_ITEM", "This item changed since you looked "
                      "at it; reload and review again.", field="revision")
    if publish and not confirm:
        raise CodedError("CONFIRM_REQUIRED", "Publishing cannot be undone: confirm it.", 400)
    try:
        return _run(actor, item, publish=publish, commit=True)
    except _DryRun as e:
        raise CodedError("PUSH_BLOCKED", "Fix these problems first; nothing was changed.", 409,
                         **e.result) from e
