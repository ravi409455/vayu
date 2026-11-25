"""Phone sign-in: the JWT access token must belong to a device that is still signed in, and a
refresh is refused once the device was signed out."""
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.errors import CodedError

from .models import Device


def _check_device(device_id: str | None) -> None:
    if device_id and not Device.objects.filter(pk=device_id, revoked_at__isnull=True).exists():
        raise CodedError("DEVICE_REVOKED", "This device was signed out.", 401)


class DeviceJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            _check_device(result[1].get("device_id"))
        return result


class DeviceCheckedRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        try:
            device_id = RefreshToken(attrs["refresh"]).get("device_id")
        except TokenError:
            device_id = None  # the parent raises the proper invalid-token error
        _check_device(device_id)
        return super().validate(attrs)
