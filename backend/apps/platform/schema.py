"""How the OpenAPI file is made (F-161): plain API views answer with a JSON object (no "unable to
guess serializer"), and the two token kinds are documented."""
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.types import OpenApiTypes


class Schema(AutoSchema):
    def _has_serializer(self) -> bool:
        view = self.view
        own = getattr(type(view), "get_serializer_class", None)
        return bool(getattr(view, "serializer_class", None)
                    or (own is not None and own is not _api_view_default()))

    def get_request_serializer(self):
        if not self._has_serializer():
            return OpenApiTypes.OBJECT if self.method in ("POST", "PUT", "PATCH") else None
        return super().get_request_serializer()

    def get_response_serializers(self):
        if not self._has_serializer():
            return OpenApiTypes.OBJECT
        return super().get_response_serializers()


def _api_view_default():
    from rest_framework.generics import GenericAPIView

    return GenericAPIView.get_serializer_class


class DeviceTokenScheme(OpenApiAuthenticationExtension):
    target_class = "apps.accounts.authentication.DeviceJWTAuthentication"
    name = "deviceToken"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "bearer", "bearerFormat": "JWT",
                "description": "The app's access token (one signed-in phone)."}


class ApiKeyScheme(OpenApiAuthenticationExtension):
    target_class = "apps.integrations.apikeys.ApiKeyAuthentication"
    name = "apiKey"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "header", "name": "Authorization",
                "description": "`Api-Key vk_...` (or the X-API-Key header)."}


def obj(name: str, **fields):
    """A named response body for the OpenAPI file: {field: serializer field}."""
    from drf_spectacular.utils import inline_serializer

    return inline_serializer(name=name, fields=fields)
