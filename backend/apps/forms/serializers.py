from rest_framework import serializers

from apps.core.errors import CodedError

from .fieldtypes import ConfigError, validate_config
from .models import (
    LIST_KEY_RE,
    Field,
    Form,
    FormKind,
    FormVersion,
    MasterList,
    MasterListItem,
    Page,
    Section,
    VersionStatus,
)


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


def _version_ref(v: FormVersion | None):
    return {"id": v.id, "number": v.number} if v else None


class FormSerializer(serializers.ModelSerializer):
    draft_version = serializers.SerializerMethodField()
    published_version = serializers.SerializerMethodField()

    class Meta:
        model = Form
        fields = ["id", "key", "kind", "name", "is_active", "draft_version", "published_version"]
        read_only_fields = ["kind"]

    def get_fields(self):
        fields = super().get_fields()
        if self.instance is None:  # kind is set once, at creation
            fields["kind"] = serializers.ChoiceField(choices=FormKind.choices)
        return fields

    def validate_key(self, value):
        if self.instance is not None and value != self.instance.key:
            raise serializers.ValidationError("A form's key can never change.")
        return _list_key(value)

    def validate(self, attrs):
        kind = attrs.get("kind") or (self.instance and self.instance.kind)
        active = attrs.get("is_active", self.instance.is_active if self.instance else True)
        if kind in (FormKind.BOOKING, FormKind.OPS) and active:
            others = Form.objects.filter(kind=kind, is_active=True)
            if self.instance:
                others = others.exclude(pk=self.instance.pk)
            if others.exists():
                raise serializers.ValidationError(f"There is already an active {kind} form.")
        return attrs

    def get_draft_version(self, obj):
        return _version_ref(obj.versions.filter(status=VersionStatus.DRAFT).first())

    def get_published_version(self, obj):
        return _version_ref(obj.versions.filter(status=VersionStatus.PUBLISHED)
                            .order_by("-number").first())


class FieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = Field
        fields = ["id", "section", "key", "label", "helper_text", "type", "config", "required",
                  "required_if", "show_if", "visible", "order", "is_system"]
        read_only_fields = ["is_system"]
        extra_kwargs = {"section": {"required": False}}

    def validate_section(self, section):
        if self.instance is not None and section.version_id != self.instance.version_id:
            raise serializers.ValidationError("Fields can only move within the same version.")
        return section

    def validate(self, attrs):
        inst = self.instance
        if inst is not None and inst.is_system and any(
                k in attrs and attrs[k] != getattr(inst, k)
                for k in ("key", "type", "config", "required", "required_if", "show_if",
                          "visible")):
            raise CodedError("SYSTEM_FIELD", "System fields can only be relabelled or moved.", 400)
        if inst is None or "config" in attrs:
            type_ = attrs.get("type", inst.type if inst else None)
            try:
                validate_config(type_, attrs.get("config", inst.config if inst else {}))
            except ConfigError as e:
                raise CodedError("INVALID_CONFIG", str(e), 400) from e
        return attrs


class SectionSerializer(serializers.ModelSerializer):
    fields = FieldSerializer(many=True, read_only=True)  # type: ignore[assignment]

    class Meta:
        model = Section
        fields = ["id", "page", "title", "order", "visible", "show_if", "fields"]
        extra_kwargs = {"page": {"required": False}}

    def validate_page(self, page):
        if self.instance is not None and page.version_id != self.instance.version_id:
            raise serializers.ValidationError("Sections can only move within the same version.")
        return page


class PageSerializer(serializers.ModelSerializer):
    sections = SectionSerializer(many=True, read_only=True)

    class Meta:
        model = Page
        fields = ["id", "title", "order", "visible", "show_if", "sections"]


class VersionTreeSerializer(serializers.ModelSerializer):
    pages = serializers.SerializerMethodField()

    class Meta:
        model = FormVersion
        fields = ["id", "form", "number", "status", "published_at", "row_version", "pages"]

    def get_pages(self, obj):
        pages = Page.objects.filter(version=obj).prefetch_related("sections__fields")
        return PageSerializer(pages, many=True).data
