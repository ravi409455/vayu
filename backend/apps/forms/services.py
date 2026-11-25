"""Form rules: create a form, drafts, publish, reorder, draft settings (switches, ratings, Key
Checks) and duplicate."""
from typing import Any

from django.db import transaction
from django.db.models import F, Max
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.accounts import audit
from apps.core.concurrency import check_row_version
from apps.core.errors import CodedError

from . import promote
from .models import (
    Field,
    Form,
    FormType,
    FormVersion,
    Page,
    Section,
    VersionCheck,
    VersionStatus,
    lock_draft,
)
from .system_fields import PAGE_TITLE, STARTER_FIELDS, SYSTEM_FIELDS


def _build_first_version(form: Form) -> FormVersion:
    """Version 1 of a new form: one page, with the locked system fields of its type and the
    ordinary fields it starts with (the wrap-up's payment questions)."""
    version = FormVersion.objects.create(form=form, number=1)
    page = Page.objects.create(version=version, title=PAGE_TITLE[form.type], order=0,
                               gate=form.type == FormType.START)
    sections: dict[str, Section] = {}
    specs = [(spec, True) for spec in SYSTEM_FIELDS.get(form.type, [])] + \
        [(spec, False) for spec in STARTER_FIELDS.get(form.type, [])]
    for order, (spec, locked) in enumerate(specs):
        spec = dict(spec)
        title = spec.pop("section", "Section 1")
        if title not in sections:
            sections[title] = Section.objects.create(version=version, page=page, title=title,
                                                     order=len(sections))
        Field.objects.create(version=version, section=sections[title], order=order,
                             is_system=locked, **{"config": {}, **spec})
    if not sections:                                          # no system fields: one empty section
        Section.objects.create(version=version, page=page, title="Section 1", order=0)
    return version


@transaction.atomic
def create_form(actor: Any, *, key: str, name: str, inspection_type: str = "") -> Form:
    """Admins create custom forms only; the booking, start and end forms exist from the start."""
    form = Form.objects.create(key=key, type=FormType.CUSTOM, name=name,
                               inspection_type=inspection_type or key)
    _build_first_version(form)
    audit.record(actor, "form.create", "form", form.id, f"Created form {key}")
    return form


SYSTEM_FORM_NAMES = {FormType.BOOKING: ("booking", "Booking"),
                     FormType.START: ("start", "Start"),
                     FormType.END: ("end", "End")}


def ensure_system_forms() -> None:
    """The booking, start and end forms: exactly one of each, always there. Safe to run again."""
    for ftype, (key, name) in SYSTEM_FORM_NAMES.items():
        if Form.objects.filter(type=ftype).exists():
            continue
        wanted, n = key, 2
        while Form.objects.filter(key=wanted).exists():
            wanted, n = f"{key}{n}", n + 1
        with transaction.atomic():
            _build_first_version(Form.objects.create(key=wanted, type=ftype, name=name))


@transaction.atomic
def create_draft(actor: Any, form: Form) -> FormVersion:
    """New draft = deep copy of the latest published version (new ids, same keys)."""
    if form.versions.filter(status=VersionStatus.DRAFT).exists():
        raise CodedError("DRAFT_EXISTS", "This form already has a draft.", 409)
    source = form.versions.filter(status=VersionStatus.PUBLISHED).order_by("-number").first()
    if source is None:
        raise CodedError("NOTHING_TO_COPY", "This form has no published version yet.", 409)
    number = (form.versions.aggregate(n=Max("number"))["n"] or 0) + 1
    draft = FormVersion.objects.create(form=form, number=number,
                                       rating_config=source.rating_config,
                                       key_checks=source.key_checks,
                                       use_start=source.use_start, use_end=source.use_end)
    for page in Page.objects.filter(version=source):
        old_page_id = page.id
        page.pk, page.version = None, draft
        page.save()
        for section in Section.objects.filter(page_id=old_page_id):
            old_section_id = section.id
            section.pk, section.version, section.page = None, draft, page
            section.save()
            for field in Field.objects.filter(section_id=old_section_id):
                field.pk, field.version, field.section = None, draft, section
                field.save()
    for check in VersionCheck.objects.filter(version=source):
        check.pk, check.version = None, draft
        check.save()
    audit.record(actor, "form.draft_create", "form", form.id,
                 f"Created draft v{number} of {form.key} from v{source.number}")
    return draft


def system_field_issues(version: FormVersion) -> list[Any]:
    from .rules import Issue

    present = {f.key: f for f in Field.objects.filter(version=version, is_system=True)}
    issues = []
    for spec in SYSTEM_FIELDS.get(version.form.type, []):
        f = present.get(spec["key"])
        if f is None:
            issues.append(Issue(f"system_fields.{spec['key']}", "MISSING_SYSTEM_FIELD",
                                f"System field '{spec['key']}' is missing."))
        elif not f.visible:
            issues.append(Issue(f"fields.{f.key}.visible", "SYSTEM_FIELD_HIDDEN",
                                f"System field '{f.key}' must stay visible."))
    return issues


def publish_version(actor: Any, version_id: int, row_version: int) -> FormVersion:
    """Freeze a draft. `row_version` must be the one the admin last saw, so nobody publishes a
    draft that changed under them. The row lock makes concurrent publishes safe."""
    from .rules import dependent_issues, validate_version

    with transaction.atomic():
        version = get_object_or_404(
            FormVersion.objects.select_for_update().select_related("form"), pk=version_id)
        if version.status == VersionStatus.PUBLISHED:
            raise CodedError("VERSION_PUBLISHED", "This version is already published.", 409)
        check_row_version(version, row_version, "STALE_DRAFT",
                          "The draft changed since you opened it; reload.")
        issues = validate_version(version) + system_field_issues(version)
        issues += dependent_issues(version)
        if issues:
            raise CodedError("PUBLISH_BLOCKED", "Fix these problems before publishing.", 400,
                             issues=[i.__dict__ for i in issues])
        from apps.scoring.service import section_keys

        version.status = VersionStatus.PUBLISHED
        version.published_at = timezone.now()
        version.row_version = F("row_version") + 1
        # whoever wrote the config (setup, promote, the demo), it goes live by section key
        version.rating_config = section_keys(version, version.rating_config)
        version.save(update_fields=["status", "published_at", "row_version", "rating_config"])
        version.refresh_from_db()
        audit.record(actor, "form.publish", "form_version", version.id,
                     f"Published {version.form.key} v{version.number}")
    return version


@transaction.atomic
def reorder(actor: Any, version_id: int, body: Any) -> FormVersion:
    """Set the order of pages, of sections inside pages, and of fields inside sections in one
    step (what dragging does). Sections and fields may move to another page or section, except
    into or out of a section linked to the library."""
    from . import library

    lock_draft(version_id)
    version = FormVersion.objects.select_for_update().get(pk=version_id)
    if not isinstance(body, dict) or set(body) - {"pages", "sections", "fields"}:
        raise CodedError("INVALID_REORDER", "Send pages, sections and/or fields.", 400)

    def ids(value: Any, label: Any) -> Any:
        if not isinstance(value, list) or not all(isinstance(i, int) for i in value) \
                or len(set(value)) != len(value):
            raise CodedError("INVALID_REORDER", f"{label} must be a list of distinct ids.", 400)
        return value

    def mine(model: Any, wanted: Any, label: Any) -> Any:
        found = {o.pk: o for o in model.objects.filter(version=version, pk__in=wanted)}
        if set(found) != set(wanted):
            raise CodedError("INVALID_REORDER", f"Some {label} are not part of this version.", 400)
        return found

    if "pages" in body:
        order = ids(body["pages"], "pages")
        pages = mine(Page, order, "pages")
        for n, pk in enumerate(order):
            if pages[pk].order != n:
                pages[pk].order = n
                pages[pk].save()
    for key, model, parent, label in (("sections", Section, "page", "sections"),
                                      ("fields", Field, "section", "fields")):
        for parent_id, order in (body.get(key) or {}).items():
            if not str(parent_id).isdigit():
                raise CodedError("INVALID_REORDER", f"{label} must be keyed by id.", 400)
            order = ids(order, label)
            owner_model = Page if parent == "page" else Section
            owner = owner_model.objects.filter(version=version, pk=int(parent_id)).first()
            if owner is None:
                raise CodedError("INVALID_REORDER", "Unknown page or section.", 400)
            found = mine(model, order, label)
            for n, pk in enumerate(order):
                obj = found[pk]
                if getattr(obj, f"{parent}_id") != owner.pk:
                    if (isinstance(obj, Field) and obj.is_system and isinstance(owner, Section)
                            and owner.page_id != obj.section.page_id):
                        raise CodedError("SYSTEM_FIELD", "System fields stay on their page.", 400)
                    if isinstance(owner, Section):                 # a field is moving
                        library.ensure_not_locked(owner)
                        library.ensure_not_locked(obj.section)
                    setattr(obj, parent, owner)
                    obj.order = n
                    obj.save()
                elif obj.order != n:
                    obj.order = n
                    obj.save()
    version.row_version += 1
    version.save(update_fields=["row_version"])
    audit.record(actor, "form.reorder", "form_version", version.id, "Reordered the form")
    return version


@transaction.atomic
def discard_draft(actor: Any, form: Form) -> None:
    """Throw the open draft away. The published version is untouched. A form that was never
    published has nothing to fall back to, so its first draft cannot be discarded."""
    draft = form.versions.filter(status=VersionStatus.DRAFT).first()
    if draft is None:
        raise CodedError("NO_DRAFT", "There is no draft to discard.", 409)
    if not form.versions.filter(status=VersionStatus.PUBLISHED).exists():
        raise CodedError("FIRST_DRAFT", "This form has never been published: there is nothing to "
                         "go back to. Publish it, or ask an Admin to deactivate the form.", 409)
    lock_draft(draft.id)
    number = draft.number
    draft.delete()
    audit.record(actor, "form.draft_discard", "form", form.id,
                 f"Discarded draft v{number} of {form.key}")


def save_draft_setting(actor: Any, version_id: int, action: str, change: Any,
                       summary: Any) -> FormVersion:
    """A setting of a draft version (switches, rating config, Key Checks), saved the one way
    (F-023): lock the draft, [change](version) sets the fields and returns their names, the
    version goes up, then the audit row says [summary](version)."""
    with transaction.atomic():
        lock_draft(version_id)
        version = get_object_or_404(FormVersion.objects.select_related("form"), pk=version_id)
        fields = change(version)
        version.row_version += 1
        version.save(update_fields=[*fields, "row_version"])
    audit.record(actor, action, "form_version", version_id, summary(version))
    return version


def save_version_settings(actor: Any, version_id: int, body: Any) -> FormVersion:
    """A custom form's two switches: begins with the start form, ends with the end form."""
    if not isinstance(body, dict) or not body or set(body) - {"use_start", "use_end"} \
            or not all(isinstance(v, bool) for v in body.values()):
        raise CodedError("INVALID_SETTINGS", "Send use_start and/or use_end as true/false.", 400)

    def change(version: FormVersion) -> list[str]:
        if version.form.type != "custom":
            raise CodedError("INVALID_SETTINGS", "Only custom forms have these settings.", 400)
        for k, v in body.items():
            setattr(version, k, v)
        return list(body)

    return save_draft_setting(
        actor, version_id, "form.settings", change,
        lambda v: f"Begins with start: {v.use_start}, ends with end: {v.use_end}")


def save_rating_config(actor: Any, version_id: int, config: Any) -> FormVersion:
    """The draft's rating config, checked, then stored by section key (F-045)."""
    from apps.scoring.engine import validate_config
    from apps.scoring.service import section_keys

    try:
        validate_config(config)
    except ValueError as e:
        raise CodedError("INVALID_RATING_CONFIG", str(e), 400) from e

    def change(version: FormVersion) -> list[str]:
        version.rating_config = section_keys(version, config)
        return ["rating_config"]

    return save_draft_setting(actor, version_id, "form.rating_config", change,
                              lambda v: "Updated rating config")


def save_key_checks(actor: Any, version_id: int, items: Any) -> FormVersion:
    """The draft's Key Checks, saved as a whole ordered list (like the rating config)."""
    from apps.scoring.keychecks import validate

    try:
        validate(items)
    except ValueError as e:
        raise CodedError("INVALID_KEY_CHECKS", str(e), 400) from e

    def change(version: FormVersion) -> list[str]:
        if items and version.form.type != "custom":       # only inspections are reviewed
            raise CodedError("INVALID_KEY_CHECKS", "Only inspection forms have Key Checks.", 400)
        version.key_checks = items
        return ["key_checks"]

    return save_draft_setting(actor, version_id, "form.key_checks", change,
                              lambda v: "Updated Key Checks")


def publish_warnings(version: FormVersion) -> list[Any]:
    """What a just-published version leaves to fix: PDF template and integration problems."""
    from apps.integrations.values import publish_warnings as integration_warnings
    from apps.reports.service import warnings as pdf_warnings

    return list(pdf_warnings(version)) + list(integration_warnings(version, published=True))


def duplicate_form(actor: Any, form: Form, key: Any, name: Any) -> dict[str, Any]:
    """A copy of [form] (newest version) as a new form with its own key and name: library
    links, ratings, Key Checks and PDF template come along; it starts as a draft."""
    latest = form.versions.order_by("-number").first()
    assert latest is not None  # noqa: S101 - a form always has its first version
    out = promote.import_bundle(actor, promote.export_bundle(latest),
                                as_new={"key": key, "name": name})
    audit.record(actor, "form.duplicate", "form", out["form"], f"Copied {form.key} as {key}")
    return out
