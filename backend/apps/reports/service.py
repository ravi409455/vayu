"""Template workflow (draft -> publish) and report lookups."""
import difflib

from django.db import transaction
from django.utils import timezone

from apps.accounts import audit
from apps.core.concurrency import check_row_version
from apps.core.errors import CodedError, fail
from apps.forms.models import Field, Form, FormType, FormVersion

from . import placeholders, shared
from .definition import (
    outer_texts,
    part_refs,
    parts,
    referenced_fields,
    referenced_sections,
    validate_definition,
)
from .models import PdfTemplate, PdfTemplateVersion

DEFAULT_DEFINITION = {"schema": 2, "filename": "{{ sys.booking_id }}.pdf", "pages": []}


def create_template(actor, form: Form) -> PdfTemplate:
    if form.type != FormType.CUSTOM:
        raise fail("INVALID_FORM", "Only inspection forms have PDF templates.")
    if PdfTemplate.objects.filter(form=form).exists():
        raise fail("TEMPLATE_EXISTS", "This form already has a PDF template.", 409)
    with transaction.atomic():
        t = PdfTemplate.objects.create(form=form)
        PdfTemplateVersion.objects.create(template=t, number=1, definition=DEFAULT_DEFINITION)
    audit.record(actor, "pdf_template.create", "pdf_template", t.id, f"Template for {form.key}")
    return t


def save_definition(actor, v: PdfTemplateVersion, definition,
                    row_version: int) -> PdfTemplateVersion:
    try:
        definition = validate_definition(definition)
    except ValueError as e:
        raise fail("INVALID_TEMPLATE", str(e)) from e
    with transaction.atomic():
        v = PdfTemplateVersion.objects.select_for_update().get(pk=v.pk)
        shared.lock_refs(definition)          # a delete of an item it uses waits for this save
        if v.status == "published":
            raise fail("VERSION_PUBLISHED", "Published templates cannot be changed.", 409)
        check_row_version(v, row_version, "STALE_DRAFT", "The draft changed since you opened it.")
        v.definition, v.row_version = definition, v.row_version + 1
        v.save()
    return v


def create_draft(actor, t: PdfTemplate) -> PdfTemplateVersion:
    if t.versions.filter(status="draft").exists():
        raise fail("DRAFT_EXISTS", "This template already has a draft.", 409)
    last = t.versions.order_by("-number").first()
    assert last is not None  # noqa: S101 - a template always has its first version
    d = PdfTemplateVersion.objects.create(template=t, number=last.number + 1,
                                          definition=last.definition)
    audit.record(actor, "pdf_template.draft_create", "pdf_template", t.id, f"Draft v{d.number}")
    return d


def _known_keys(template: PdfTemplate) -> dict[str, set[str]]:
    from apps.bookings.services import booking_form_version
    from apps.bookings.submissions import system_version

    def keys(version):
        return set(Field.objects.filter(version=version).values_list("key", flat=True)) \
            if version else set()

    latest = FormVersion.objects.filter(form=template.form).order_by("-number").first()
    try:
        booking = booking_form_version()
    except CodedError:
        booking = None
    # a form that does not begin / end with the start / end form cannot show their answers
    use_start = latest is None or latest.use_start
    use_end = latest is None or latest.use_end
    return {"inspection": keys(latest), "booking": keys(booking),
            "check": {k["key"] for k in (latest.key_checks if latest else [])
                      if k.get("in_report", True)},
            "start": keys(system_version("start")) if use_start else set(),
            "end": keys(system_version("end")) if use_end else set()}


def _section_keys(template: PdfTemplate) -> set[str]:
    from apps.forms.models import Section

    latest = FormVersion.objects.filter(form=template.form).order_by("-number").first()
    return set(Section.objects.filter(version=latest).values_list("key", flat=True))


def _close(key: str, choices: set[str]) -> str | None:
    found = difflib.get_close_matches(key, sorted(choices), n=1, cutoff=0.6)
    return found[0] if found else None


def definition_issues(template: PdfTemplate, definition: dict) -> list[dict]:
    """Parts of a layout (its shared theme and parts included) that point at fields or sections
    the form (as it is now, draft or live) lacks, or at shared items this server does not have.
    Each names its part, and the closest field or section the form does have."""
    known = _known_keys(template)
    sections = _section_keys(template)
    out = shared.missing(definition)
    resolved = shared.resolve(definition)
    outer: set[tuple[str, str]] = set()
    for _, text in outer_texts(resolved):
        outer |= placeholders.refs(text)
    found: list[tuple[str, str | None, set[tuple[str, str]], set[str]]] = [
        ("definition", None, outer, set())] + [
        (where, p.get("id"), *part_refs(p)) for where, p in parts(resolved)]
    for where, pid, fields, secs in found:
        for key in sorted(secs - sections):
            out.append({"path": where, "part": pid, "code": "UNKNOWN_SECTION",
                        "ref": f"inspection.{key}", "suggestion": _suggest("inspection",
                                                                           _close(key, sections)),
                        "message": f"Section '{key}' is not a section of the form."})
        for form, key in sorted(fields):
            if key in known.get(form, set()):
                continue
            out.append({"path": where, "part": pid, "code": "UNKNOWN_FIELD",
                        "ref": f"{form}.{key}",
                        "suggestion": _suggest(form, _close(key, known.get(form, set()))),
                        "message": (f"'{key}' is not a Key Check the report may show."
                                    if form == "check" else
                                    f"'{form}.{key}' needs the {form} form, which this form does "
                                    "not include (see its form settings)."
                                    if form in ("start", "end") and not known.get(form)
                                    else f"'{form}.{key}' is not a field of the {form} form.")})
    return out


def _suggest(form: str, key: str | None) -> str | None:
    return f"{form}.{key}" if key else None


def latest_layout_issues(form: Form) -> list[dict]:
    """The form's newest PDF layout against the form's newest version (used before a library
    push goes live)."""
    template = PdfTemplate.objects.filter(form=form).first()
    last = template.versions.order_by("-number").first() if template else None
    return definition_issues(template, last.definition) if template and last else []


def publish(actor, v: PdfTemplateVersion, row_version: int) -> PdfTemplateVersion:
    with transaction.atomic():
        v = PdfTemplateVersion.objects.select_for_update().select_related(
            "template__form").get(pk=v.pk)
        if v.status == "published":
            raise fail("VERSION_PUBLISHED", "Already published.", 409)
        check_row_version(v, row_version, "STALE_DRAFT", "The draft changed since you opened it.")
        issues = definition_issues(v.template, v.definition)
        if issues:
            raise fail("PUBLISH_BLOCKED", "Fix these problems before publishing.", issues=issues)
        v.status, v.published_at, v.row_version = "published", timezone.now(), v.row_version + 1
        v.save()
        audit.record(actor, "pdf_template.publish", "pdf_template", v.template_id,
                     f"Published {v.template.form.key} template v{v.number}")
    return v


def warnings(version: FormVersion) -> list[dict]:
    """Form fields the form's PDF template never shows (informational; publishing proceeds)."""
    t = PdfTemplate.objects.filter(form=version.form).first()
    last = t.versions.order_by("-number").first() if t else None
    if last is None:
        return []
    resolved = shared.resolve(last.definition)
    used = {key for form, key in referenced_fields(resolved) if form == "inspection"}
    whole = referenced_sections(resolved)
    return [{"code": "FIELD_NOT_IN_PDF", "key": k,
             "message": f"Field '{k}' is not shown in the PDF template."}
            for k, section in Field.objects.filter(version=version).order_by("id")
            .values_list("key", "section__key") if k not in used and section not in whole]


def discard_draft(actor, v: PdfTemplateVersion) -> None:
    """Throw an unpublished layout away. The first version has nothing to fall back to."""
    with transaction.atomic():
        v = PdfTemplateVersion.objects.select_for_update().select_related(
            "template__form").get(pk=v.pk)
        if v.status != "draft":
            raise fail("NOT_A_DRAFT", "Only a draft can be discarded.", 409)
        if not v.template.versions.filter(status="published").exists():
            raise fail("FIRST_DRAFT", "This template was never published: there is nothing to go "
                       "back to.", 409)
        number, key = v.number, v.template.form.key
        v.delete()
        audit.record(actor, "pdf_template.draft_discard", "pdf_template", v.template_id,
                     f"Discarded {key} template draft v{number}")


def unused_fields(template: PdfTemplate, definition: dict) -> list[dict]:
    """Fields of the form (as it is now) that this layout never shows."""
    latest = FormVersion.objects.filter(form=template.form).order_by("-number").first()
    resolved = shared.resolve(definition)
    used = {key for form, key in referenced_fields(resolved) if form == "inspection"}
    whole = referenced_sections(resolved)
    return [{"key": k, "label": label, "section": title}
            for k, label, sec, title in Field.objects.filter(version=latest)
            .exclude(type__in=("image", "form_choice")).order_by("section__page__order",
                                                                 "section__order", "order")
            .values_list("key", "label", "section__key", "section__title")
            if k not in used and sec not in whole]
