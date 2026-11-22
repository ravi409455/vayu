import re

from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.core.errors import CodedError

KEY_RE = re.compile(r"[a-z][a-z0-9_]{1,62}")       # field keys: 2-63 chars
LIST_KEY_RE = re.compile(r"[a-z][a-z0-9_]{0,63}")  # master list / item keys: 1-64 chars


class MasterList(models.Model):
    key = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=150)


class MasterListItem(models.Model):
    list = models.ForeignKey(MasterList, on_delete=models.CASCADE, related_name="items")
    key = models.CharField(max_length=64)
    label = models.CharField(max_length=200)
    order = models.IntegerField(default=0)
    archived = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["list", "key"], name="item_key_per_list")]
        ordering = ["order", "id"]


class FormKind(models.TextChoices):
    BOOKING = "booking"
    OPS = "ops"
    INSPECTION = "inspection"


class Form(models.Model):
    key = models.CharField(max_length=64, unique=True)
    kind = models.CharField(max_length=16, choices=FormKind.choices)
    name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["kind"], condition=Q(is_active=True, kind__in=["booking", "ops"]),
            name="one_active_booking_and_ops_form")]


class VersionStatus(models.TextChoices):
    DRAFT = "draft"
    PUBLISHED = "published"


class FormVersion(models.Model):
    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name="versions")
    number = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=VersionStatus.choices,
                              default=VersionStatus.DRAFT)
    created_at = models.DateTimeField(default=timezone.now)
    published_at = models.DateTimeField(null=True, blank=True)
    row_version = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["form", "number"], name="version_number_per_form"),
            models.UniqueConstraint(fields=["form"], condition=Q(status="draft"),
                                    name="one_draft_per_form"),
        ]


class LibraryKind(models.TextChoices):
    FIELD = "field"
    SECTION = "section"


class LibraryItem(models.Model):
    """A reusable field or section. Forms link to it (copying its content at that revision) and
    pull later edits only when an admin accepts them."""

    kind = models.CharField(max_length=10, choices=LibraryKind.choices)
    key = models.CharField(max_length=64)
    name = models.CharField(max_length=200)
    definition = models.JSONField()
    revision = models.PositiveIntegerField(default=1)
    archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["kind", "key"], name="library_key_per_kind")]
        ordering = ["kind", "key"]


def ensure_draft(version_id: int) -> None:
    status = FormVersion.objects.filter(pk=version_id).values_list("status", flat=True).first()
    if status == VersionStatus.PUBLISHED:
        raise CodedError("VERSION_PUBLISHED", "Published versions cannot be changed.", 409)


class DraftOnly(models.Model):
    """Pages, sections, fields and checks may only change while their version is a draft."""

    version = models.ForeignKey(FormVersion, on_delete=models.CASCADE, related_name="+")

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        ensure_draft(self.version_id)
        super().save(*args, **kwargs)
        self._bump_row_version()

    def delete(self, *args, **kwargs):
        ensure_draft(self.version_id)
        result = super().delete(*args, **kwargs)
        self._bump_row_version()
        return result

    def _bump_row_version(self) -> None:
        """Every draft change moves row_version, so a publish can prove it saw the latest."""
        FormVersion.objects.filter(pk=self.version_id).update(row_version=F("row_version") + 1)


class Page(DraftOnly):
    title = models.CharField(max_length=150)
    order = models.IntegerField(default=0)
    visible = models.BooleanField(default=True)
    show_if = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["order", "id"]

    def delete(self, *args, **kwargs):
        ensure_draft(self.version_id)
        if Field.objects.filter(section__page=self, is_system=True).exists():
            raise CodedError("SYSTEM_FIELD", "This page holds system fields; move them first.", 400)
        return super().delete(*args, **kwargs)


class Section(DraftOnly):
    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name="sections")
    title = models.CharField(max_length=150)
    order = models.IntegerField(default=0)
    visible = models.BooleanField(default=True)
    show_if = models.JSONField(null=True, blank=True)
    library_item = models.ForeignKey(LibraryItem, null=True, blank=True, on_delete=models.PROTECT,
                                     related_name="linked_sections")
    library_revision = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["order", "id"]

    def delete(self, *args, **kwargs):
        ensure_draft(self.version_id)
        if self.fields.filter(is_system=True).exists():
            raise CodedError("SYSTEM_FIELD", "This section holds system fields; move them first.",
                             400)
        return super().delete(*args, **kwargs)


class FieldType(models.TextChoices):
    SINGLE_CHOICE = "single_choice"
    MULTI_CHOICE = "multi_choice"
    YES_NO = "yes_no"
    MASTER_LIST = "master_list"
    USER_PICKER = "user_picker"
    SHORT_TEXT = "short_text"
    LONG_TEXT = "long_text"
    NUMBER = "number"
    CURRENCY = "currency"
    PHONE = "phone"
    DATE = "date"
    TIME = "time"
    DATETIME = "datetime"
    GPS = "gps"
    PHOTO = "photo"
    VIDEO = "video"
    FILE = "file"
    SIGNATURE = "signature"
    DERIVED = "derived"  # system-filled (Key Checks), Ops can override
    RATING = "rating"    # system-filled (suggested rating), Ops can override


class FieldKey(models.Model):
    """Every key ever used in a form, with its type. A deleted field's key stays reserved, so a
    key always means the same thing across versions (API, webhooks and PDFs rely on it)."""

    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name="field_keys")
    key = models.CharField(max_length=63)
    type = models.CharField(max_length=20, choices=FieldType.choices)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["form", "key"], name="key_per_form")]


SYSTEM_PROTECTED = ("key", "type", "config", "required", "required_if", "show_if", "visible",
                    "is_system")


class Field(DraftOnly):
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="fields")
    key = models.CharField(max_length=63)
    label = models.CharField(max_length=200)
    helper_text = models.TextField(blank=True)
    type = models.CharField(max_length=20, choices=FieldType.choices)
    config = models.JSONField(default=dict, blank=True)
    required = models.BooleanField(default=False)
    required_if = models.JSONField(null=True, blank=True)
    show_if = models.JSONField(null=True, blank=True)
    visible = models.BooleanField(default=True)
    order = models.IntegerField(default=0)
    is_system = models.BooleanField(default=False)
    library_item = models.ForeignKey(LibraryItem, null=True, blank=True, on_delete=models.PROTECT,
                                     related_name="linked_fields")
    library_revision = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["order", "id"]
        constraints = [models.UniqueConstraint(fields=["version", "key"], name="key_per_version")]

    def save(self, *args, **kwargs):
        ensure_draft(self.version_id)
        if self.section.version_id != self.version_id:
            raise CodedError("WRONG_VERSION", "Section belongs to another form version.", 400)
        if self.pk is None:
            self._check_new_key()
        else:
            self._check_immutable()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        ensure_draft(self.version_id)
        if self.is_system:
            raise CodedError("SYSTEM_FIELD", "System fields cannot be removed.", 400)
        return super().delete(*args, **kwargs)

    def _check_new_key(self):
        if not KEY_RE.fullmatch(self.key or ""):
            raise CodedError("INVALID_KEY", "Key must be 2-63 chars: a-z, 0-9, _, starting with "
                             "a letter.", 400)
        if Field.objects.filter(version_id=self.version_id, key=self.key).exists():
            raise CodedError("DUPLICATE_KEY", f"Key '{self.key}' is already used in this form.",
                             400)
        form_id = FormVersion.objects.values_list("form_id", flat=True).get(pk=self.version_id)
        reserved, _ = FieldKey.objects.get_or_create(form_id=form_id, key=self.key,
                                                     defaults={"type": self.type})
        if reserved.type != self.type:
            raise CodedError("KEY_RESERVED", f"Key '{self.key}' was used before as a "
                             f"{reserved.type} field; pick another key.", 400)

    def _check_immutable(self):
        old = Field.objects.filter(pk=self.pk).values(*SYSTEM_PROTECTED).first()
        if old is None:
            return
        if old["key"] != self.key:
            raise CodedError("KEY_IMMUTABLE", "A field's key can never change.", 400)
        if old["type"] != self.type:
            raise CodedError("TYPE_IMMUTABLE", "A field's type can never change; add a new "
                             "field instead.", 400)
        if old["is_system"] and any(old[a] != getattr(self, a) for a in SYSTEM_PROTECTED):
            raise CodedError("SYSTEM_FIELD", "System fields can only be relabelled or moved.", 400)


class VersionCheck(DraftOnly):
    """Cross-field check: when `rule` is falsy, each field in `fields` gets `message`."""

    rule = models.JSONField()
    message = models.CharField(max_length=300)
    fields = models.JSONField(default=list)  # own-form field keys
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
