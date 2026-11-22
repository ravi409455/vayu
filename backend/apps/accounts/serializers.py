from rest_framework import serializers

from .models import AuditLog, Role, User
from .services import validate_new_password


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = ["id", "username", "name", "email", "role", "is_active",
                  "must_change_password", "locked_until", "password"]
        read_only_fields = ["must_change_password", "locked_until"]

    def validate_username(self, value):
        value = value.strip()
        if self.instance is None and User.objects.filter(username__iexact=value).exists():
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


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()
    client = serializers.ChoiceField(choices=["web", "mobile"])
    device_name = serializers.CharField(required=False, allow_blank=True, default="")


class PasswordSerializer(serializers.Serializer):
    password = serializers.CharField()


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField()


class AuditLogSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", read_only=True, default=None)

    class Meta:
        model = AuditLog
        fields = ["id", "actor", "actor_username", "action", "target_type", "target_id",
                  "summary", "created_at"]


ROLE_VALUES = [r.value for r in Role]
