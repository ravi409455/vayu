from rest_framework import serializers

from apps.core.errors import CodedError

from . import library
from .access import validate_access
from .fieldtypes import ConfigError, validate_config
from .models import (
    LIST_KEY_RE,
    Field,
    Form,
    FormType,
    FormVersion,
    LibraryItem,
    MasterList,
    MasterListItem,
    Page,
    Section,
    VersionCheck,
    VersionStatus,
    only_choices_changed,
)
from .rules import rule_syntax_issues


def _list_key(value: str) -> str:
    if not LIST_KEY_RE.fullmatch(value or ""):
        raise serializers.ValidationError("Use lowercase letters, digits and _; start with a "
                                          "letter; max 64 characters.")
    return value


class MasterListSerializer(serializers.ModelSerializer):
    class Meta:
        model = MasterList
        fields = ["id", "key", "name"]

    def validate_key(self, value):
        if self.instance is not None and value != self.instance.key:
            raise serializers.ValidationError("A list's key can never change.")
        return _list_key(value)


class MasterListItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = MasterListItem
        fields = ["id", "key", "label", "order", "archived"]

    def validate_key(self, value):
        if self.instance is not None and value != self.instance.key:
            raise serializers.ValidationError("An item's key can never change.")
        value = _list_key(value)
        list_obj = self.context.get("list")
        if self.instance is None and list_obj and list_obj.items.filter(key=value).exists():
            raise serializers.ValidationError("This key already exists in the list.")
        return value


def _check_rules(attrs: dict, *names: str) -> None:
    for name in names:
        if name in attrs:
            issues = rule_syntax_issues(attrs[name], name)
            if issues:
                raise CodedError("INVALID_RULE", "; ".join(f"{i.path}: {i.message}"
                                                           for i in issues), 400)


def _check_access(attrs: dict) -> None:
    if "access" in attrs:
        try:
            validate_access(attrs["access"])
        except ValueError as e:
            raise CodedError("INVALID_ACCESS", str(e), 400) from e


def _version_ref(v: FormVersion | None):
    return ({"id": v.id, "number": v.number, "use_start": v.use_start, "use_end": v.use_end}
            if v else None)


class FormSerializer(serializers.ModelSerializer):
    draft_version = serializers.SerializerMethodField()
    published_version = serializers.SerializerMethodField()

    class Meta:
        model = Form
        fields = ["id", "key", "type", "name", "is_active", "inspection_type", "submission_roles",
                  "draft_version", "published_version"]
        read_only_fields = ["type", "inspection_type"]

    def validate_key(self, value):
        if self.instance is not None and value != self.instance.key:
            raise serializers.ValidationError("A form's key can never change.")
        return _list_key(value)

    def validate_submission_roles(self, value):
        if (not isinstance(value, list) or set(value) - {"expert", "ops"}
                or len(set(value)) != len(value)):
            raise serializers.ValidationError("Choose from expert and ops (Admin always can).")
        return value

    def validate(self, attrs):
        # Admins create custom forms only; the booking, start and end forms already exist
        wanted = self.initial_data.get("type", FormType.CUSTOM) if self.instance is None else None
        if self.instance is None and wanted != FormType.CUSTOM:
            raise serializers.ValidationError(
                {"type": "Only custom forms can be created; the booking, start and end forms "
                         "already exist."})
        form_type = self.instance.type if self.instance else FormType.CUSTOM
        if "submission_roles" in attrs and form_type != FormType.CUSTOM:
            raise serializers.ValidationError("Only custom forms have submissions to share.")
        if self.instance is not None and self.instance.is_system \
                and attrs.get("is_active") is False:
            raise CodedError("SYSTEM_FORM", "The booking, start and end forms cannot be "
                                            "switched off.", 400)
        return attrs

    def get_draft_version(self, obj):
        return _version_ref(obj.versions.filter(status=VersionStatus.DRAFT).first())

    def get_published_version(self, obj):
        return _version_ref(obj.versions.filter(status=VersionStatus.PUBLISHED)
                            .order_by("-number").first())


def _library_info(obj, context) -> dict | None:
    item = obj.library_item
    if item is None:
        return None
    draft = context.get("draft")
    if draft is None:
        draft = obj.version.status == VersionStatus.DRAFT
    return {"item": item.id, "revision": obj.library_revision,
            "update_available": bool(draft and item.revision > (obj.library_revision or 0))}


class FieldSerializer(serializers.ModelSerializer):
    library = serializers.SerializerMethodField()
    locked = serializers.SerializerMethodField()

    class Meta:
        model = Field
        fields = ["id", "section", "key", "label", "helper_text", "type", "config", "required",
                  "required_if", "show_if", "visible", "order", "is_system", "access", "library",
                  "locked"]
        read_only_fields = ["is_system"]
        extra_kwargs = {"section": {"required": False}}

    def get_library(self, obj):
        return _library_info(obj, self.context)

    def get_locked(self, obj):
        return library.locked(obj)

    def validate_section(self, section):
        inst = self.instance
        if inst is not None and section.version_id != inst.version_id:
            raise serializers.ValidationError("Fields can only move within the same version.")
        if inst is not None and section.pk != inst.section_id and (
                section.library_item_id or inst.section.library_item_id):
            raise CodedError("LINKED_LOCKED", "Fields cannot move into or out of a section "
                             "linked to the library.", 409)
        return section

    def validate(self, attrs):
        inst = self.instance
        if inst is not None and library.locked(inst) and any(
                k in attrs and attrs[k] != getattr(inst, k)
                for k in ("label", "helper_text", "config", "type")):
            raise CodedError("LINKED_LOCKED", "This field's content comes from the library; "
                             "unlink it or edit the library item.", 409)
        if inst is not None and inst.is_system and (any(
                k in attrs and attrs[k] != getattr(inst, k)
                for k in ("key", "type", "required", "required_if", "show_if", "visible")) or (
                "config" in attrs and not only_choices_changed(inst.type, inst.config,
                                                                attrs["config"]))):
            raise CodedError("SYSTEM_FIELD", "System fields can only be relabelled, moved, or "
                             "(for a choice) given other choices.", 400)
        _check_rules(attrs, "show_if", "required_if")
        _check_access(attrs)
        if inst is None or "config" in attrs:
            type_ = attrs.get("type", inst.type if inst else None)
            config = attrs.get("config", inst.config if inst else {})
            try:
                validate_config(type_, config)
            except ConfigError as e:
                raise CodedError("INVALID_CONFIG", str(e), 400) from e
            if type_ == "derived":
                _check_rules({"config.rule": config["rule"]}, "config.rule")
        return attrs


class SectionSerializer(serializers.ModelSerializer):
    fields = FieldSerializer(many=True, read_only=True)  # type: ignore[assignment]
    library = serializers.SerializerMethodField()
    locked = serializers.SerializerMethodField()

    class Meta:
        model = Section
        fields = ["id", "page", "key", "title", "order", "visible", "show_if", "access",
                  "fields", "library", "locked"]
        read_only_fields = ["key"]
        extra_kwargs = {"page": {"required": False}}

    def get_library(self, obj):
        return _library_info(obj, self.context)

    def get_locked(self, obj):
        return obj.library_item_id is not None

    def validate(self, attrs):
        inst = self.instance
        if inst is not None and inst.library_item_id and "title" in attrs \
                and attrs["title"] != inst.title:
            raise CodedError("LINKED_LOCKED", "This section's content comes from the library.",
                             409)
        _check_rules(attrs, "show_if")
        _check_access(attrs)
        return attrs

    def validate_page(self, page):
        if self.instance is not None and page.version_id != self.instance.version_id:
            raise serializers.ValidationError("Sections can only move within the same version.")
        return page

    def update(self, instance, validated_data):
        from django.db import transaction

        from .ratings import rename_section_title

        old = instance.title
        with transaction.atomic():
            section = super().update(instance, validated_data)
            if section.title != old:
                rename_section_title(section.version_id, old, section.title)
        return section


class PageSerializer(serializers.ModelSerializer):
    sections = SectionSerializer(many=True, read_only=True)

    class Meta:
        model = Page
        fields = ["id", "title", "order", "visible", "gate", "show_if", "access",
                  "sections"]

    def validate(self, attrs):
        _check_rules(attrs, "show_if")
        _check_access(attrs)
        return attrs


class CheckSerializer(serializers.ModelSerializer):
    message = serializers.CharField(allow_blank=True, max_length=300)

    class Meta:
        model = VersionCheck
        fields = ["id", "rule", "message", "fields", "order"]

    def validate(self, attrs):
        if "message" in attrs and not attrs["message"].strip():
            raise CodedError("INVALID_CHECK", "A check needs a message.", 400)
        if "fields" in attrs and (not isinstance(attrs["fields"], list) or not attrs["fields"]
                                  or not all(isinstance(k, str) for k in attrs["fields"])):
            raise CodedError("INVALID_CHECK", "A check needs at least one field key.", 400)
        _check_rules(attrs, "rule")
        return attrs


class VersionTreeSerializer(serializers.ModelSerializer):
    pages = serializers.SerializerMethodField()

    class Meta:
        model = FormVersion
        fields = ["id", "form", "number", "status", "published_at", "row_version", "pages",
                  "checks", "rating_config", "key_checks", "use_start", "use_end"]

    checks = serializers.SerializerMethodField()

    def get_checks(self, obj):
        return CheckSerializer(VersionCheck.objects.filter(version=obj), many=True).data

    def get_pages(self, obj):
        pages = Page.objects.filter(version=obj).prefetch_related(
            "sections__library_item", "sections__fields__library_item",
            "sections__fields__section")
        return PageSerializer(pages, many=True,
                              context={"draft": obj.status == VersionStatus.DRAFT}).data


class LibraryItemSerializer(serializers.ModelSerializer):
    used_in = serializers.SerializerMethodField()

    class Meta:
        model = LibraryItem
        fields = ["id", "kind", "key", "name", "definition", "revision", "archived", "used_in"]

    def get_used_in(self, obj):
        """How many forms use this item."""
        return len({u["form"] for u in library.usages(obj)})


class LibraryItemDetailSerializer(LibraryItemSerializer):
    usages = serializers.SerializerMethodField()

    class Meta(LibraryItemSerializer.Meta):
        fields = [*LibraryItemSerializer.Meta.fields, "usages"]

    def get_usages(self, obj):
        return library.usages(obj)
