"""Request and response bodies for sign-in, the current user, users, passwords and the audit log."""
from rest_framework import serializers

from apps.core.phone import InvalidPhone, normalize

from .models import AuditLog, User
from .services import validate_new_password


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    avatar_url = serializers.SerializerMethodField()
    phone = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ["id", "username", "name", "email", "role", "is_active",
                  "must_change_password", "locked_until", "password", "phone", "avatar_url",
                  "last_login"]
        read_only_fields = ["must_change_password", "locked_until", "last_login"]

    def get_avatar_url(self, obj) -> str | None:
        """Where this person's picture is served from (the version busts the browser's cache);
        null when they have none."""
        if not obj.has_avatar:
            return None
        return f"/api/v1/users/{obj.pk}/picture?v={obj.avatar_version}"

    def validate_phone(self, value):
        """The same Indian mobile format as customer phones, stored as +91XXXXXXXXXX."""
        if not value.strip():
            return ""
        try:
            return normalize(value)
        except InvalidPhone as e:
            raise serializers.ValidationError(str(e)) from e

    def validate_username(self, value):
        value = value.strip()
        if self.instance is not None:
            if value != self.instance.username:  # also blocks case-variant clashes (DB 500)
                raise serializers.ValidationError("Usernames cannot be changed.")
        elif User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("Username already taken.")
        return value

    def validate(self, attrs):
        if self.instance is None:
            if "password" not in attrs:
                raise serializers.ValidationError({"password": "This field is required."})
            validate_new_password(attrs["password"], attrs["username"])
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        return User.objects.create_user(password=password, **validated_data)

    def update(self, instance, validated_data):
        validated_data.pop("password", None)  # passwords change via the dedicated endpoints
        return super().update(instance, validated_data)


class MeSerializer(UserSerializer):
    """The signed-in person's own record: adds their saved theme."""

    class Meta(UserSerializer.Meta):
        fields = [*UserSerializer.Meta.fields, "theme", "notify_prefs"]
        read_only_fields = [*UserSerializer.Meta.read_only_fields, "theme", "notify_prefs"]


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()
    client = serializers.ChoiceField(choices=["web", "mobile"])
    device_name = serializers.CharField(required=False, allow_blank=True, default="")
    # the app's install (see Device.install_id); older apps don't send it
    install_id = serializers.UUIDField(required=False, allow_null=True, default=None,
                                       write_only=True)


class PasswordSerializer(serializers.Serializer):
    password = serializers.CharField()


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField()


class AuditLogSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", read_only=True, default=None)
    actor_name = serializers.CharField(source="actor.shown_name", read_only=True, default=None)

    class Meta:
        model = AuditLog
        fields = ["id", "actor", "actor_username", "actor_name", "action", "target_type",
                  "target_id", "summary", "created_at"]


