from django.db import transaction
from django.db.models import F, Max
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.accounts import audit
from apps.core.errors import CodedError

from .models import (
    Field,
    Form,
    FormVersion,
    MasterListItem,
    Page,
    Section,
    VersionCheck,
    VersionStatus,
)
from .system_fields import SYSTEM_FIELDS


def item_label(list_key: str, item_key: str) -> str | None:
    """Label for a master-list item, archived or not (old answers must still display)."""
    return (MasterListItem.objects.filter(list__key=list_key, key=item_key)
            .values_list("label", flat=True).first())


@transaction.atomic
def create_form(actor, *, key: str, kind: str, name: str, inspection_type: str = "") -> Form:
    form = Form.objects.create(key=key, kind=kind, name=name, inspection_type=inspection_type)
    version = FormVersion.objects.create(form=form, number=1)
    page = Page.objects.create(version=version, title="Page 1", order=0)
    section = Section.objects.create(version=version, page=page, title="Section 1", order=0)
    for order, spec in enumerate(SYSTEM_FIELDS[kind]):
        Field.objects.create(version=version, section=section, order=order, is_system=True,
                             **{"config": {}, **spec})
    audit.record(actor, "form.create", "form", form.id, f"Created {kind} form {key}")
    return form


@transaction.atomic
def create_draft(actor, form: Form) -> FormVersion:
    """New draft = deep copy of the latest published version (new ids, same keys)."""
    if form.versions.filter(status=VersionStatus.DRAFT).exists():
        raise CodedError("DRAFT_EXISTS", "This form already has a draft.", 409)
    source = form.versions.filter(status=VersionStatus.PUBLISHED).order_by("-number").first()
    if source is None:
        raise CodedError("NOTHING_TO_COPY", "This form has no published version yet.", 409)
    number = (form.versions.aggregate(n=Max("number"))["n"] or 0) + 1
    draft = FormVersion.objects.create(form=form, number=number)
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


def system_field_issues(version: FormVersion) -> list:
    from .rules import Issue

    present = {f.key: f for f in Field.objects.filter(version=version, is_system=True)}
    issues = []
    for spec in SYSTEM_FIELDS[version.form.kind]:
        f = present.get(spec["key"])
        if f is None:
            issues.append(Issue(f"system_fields.{spec['key']}", "MISSING_SYSTEM_FIELD",
                                f"System field '{spec['key']}' is missing."))
        elif not f.visible:
            issues.append(Issue(f"fields.{f.key}.visible", "SYSTEM_FIELD_HIDDEN",
                                f"System field '{f.key}' must stay visible."))
    return issues


def publish_version(actor, version_id: int, row_version: int) -> FormVersion:
    """Freeze a draft. `row_version` must be the one the admin last saw, so nobody publishes a
    draft that changed under them. The row lock makes concurrent publishes safe."""
    from .rules import dependent_issues, validate_version

    with transaction.atomic():
        version = get_object_or_404(
            FormVersion.objects.select_for_update().select_related("form"), pk=version_id)
        if version.status == VersionStatus.PUBLISHED:
            raise CodedError("VERSION_PUBLISHED", "This version is already published.", 409)
        if row_version != version.row_version:
            raise CodedError("STALE_DRAFT", "The draft changed since you opened it; reload.",
                             409, row_version=version.row_version)
        issues = validate_version(version) + system_field_issues(version)
        issues += dependent_issues(version)
        if issues:
            raise CodedError("PUBLISH_BLOCKED", "Fix these problems before publishing.", 400,
                             issues=[i.__dict__ for i in issues])
        version.status = VersionStatus.PUBLISHED
        version.published_at = timezone.now()
        version.row_version = F("row_version") + 1
        version.save(update_fields=["status", "published_at", "row_version"])
        version.refresh_from_db()
        audit.record(actor, "form.publish", "form_version", version.id,
                     f"Published {version.form.key} v{version.number}")
    return version
