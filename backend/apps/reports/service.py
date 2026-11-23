"""Template workflow (draft -> publish) and report lookups."""
from django.db import transaction
from django.utils import timezone

from apps.accounts import audit
from apps.bookings.services import err
from apps.core.errors import CodedError
from apps.forms.models import Field, Form, FormType, FormVersion

from .definition import referenced_fields, validate_definition
from .models import PdfTemplate, PdfTemplateVersion

DEFAULT_DEFINITION = {"filename": "{booking_id}{type_code}.pdf", "type_code": "", "blocks": []}


def create_template(actor, form: Form) -> PdfTemplate:
    if form.type != FormType.CUSTOM:
        raise err("INVALID_FORM", "Only inspection forms have PDF templates.")
    if PdfTemplate.objects.filter(form=form).exists():
        raise err("TEMPLATE_EXISTS", "This form already has a PDF template.", 409)
    with transaction.atomic():
        t = PdfTemplate.objects.create(form=form)
        PdfTemplateVersion.objects.create(template=t, number=1, definition=DEFAULT_DEFINITION)
    audit.record(actor, "pdf_template.create", "pdf_template", t.id, f"Template for {form.key}")
    return t


def save_definition(actor, v: PdfTemplateVersion, definition,
                    row_version: int) -> PdfTemplateVersion:
    try:
        validate_definition(definition)
    except ValueError as e:
        raise err("INVALID_TEMPLATE", str(e)) from e
    with transaction.atomic():
        v = PdfTemplateVersion.objects.select_for_update().get(pk=v.pk)
        if v.status == "published":
            raise err("VERSION_PUBLISHED", "Published templates cannot be changed.", 409)
        if row_version != v.row_version:
            raise err("STALE_DRAFT", "The draft changed since you opened it.", 409,
                      row_version=v.row_version)
        v.definition, v.row_version = definition, v.row_version + 1
        v.save()
    return v


def create_draft(actor, t: PdfTemplate) -> PdfTemplateVersion:
    if t.versions.filter(status="draft").exists():
        raise err("DRAFT_EXISTS", "This template already has a draft.", 409)
    last = t.versions.order_by("-number").first()
    assert last is not None  # a template always has its first version
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
            "start": keys(system_version("start")) if use_start else set(),
            "end": keys(system_version("end")) if use_end else set()}


def publish(actor, v: PdfTemplateVersion, row_version: int) -> PdfTemplateVersion:
    with transaction.atomic():
        v = PdfTemplateVersion.objects.select_for_update().select_related(
            "template__form").get(pk=v.pk)
        if v.status == "published":
            raise err("VERSION_PUBLISHED", "Already published.", 409)
        if row_version != v.row_version:
            raise err("STALE_DRAFT", "The draft changed since you opened it.", 409,
                      row_version=v.row_version)
        known = _known_keys(v.template)
        issues = [{"path": "definition", "code": "UNKNOWN_FIELD",
                   "message": (f"'{form}.{key}' needs the {form} form, which this form does not "
                               "include (see its form settings)."
                               if form in ("start", "end") and not known.get(form)
                               else f"'{form}.{key}' is not a field of the {form} form.")}
                  for form, key in sorted(referenced_fields(v.definition))
                  if key not in known.get(form, set())]
        if issues:
            raise err("PUBLISH_BLOCKED", "Fix these problems before publishing.", issues=issues)
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
    used = {key for form, key in referenced_fields(last.definition) if form == "inspection"}
    return [{"code": "FIELD_NOT_IN_PDF", "key": k,
             "message": f"Field '{k}' is not shown in the PDF template."}
            for k in Field.objects.filter(version=version).order_by("id")
            .values_list("key", flat=True) if k not in used]


def discard_draft(actor, v: PdfTemplateVersion) -> None:
    """Throw an unpublished layout away. The first version has nothing to fall back to."""
    with transaction.atomic():
        v = PdfTemplateVersion.objects.select_for_update().select_related(
            "template__form").get(pk=v.pk)
        if v.status != "draft":
            raise err("NOT_A_DRAFT", "Only a draft can be discarded.", 409)
        if not v.template.versions.filter(status="published").exists():
            raise err("FIRST_DRAFT", "This template was never published: there is nothing to go "
                      "back to.", 409)
        number, key = v.number, v.template.form.key
        v.delete()
        audit.record(actor, "pdf_template.draft_discard", "pdf_template", v.template_id,
                     f"Discarded {key} template draft v{number}")
