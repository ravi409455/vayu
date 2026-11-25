"""API keys: a long random secret shown once, stored only as a SHA-256 hash."""
import hashlib
import secrets
from typing import Any

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request

from apps.accounts.models import Role, User

from .models import ApiKey

SERVICE_USERNAME = "api-key-service"


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def generate() -> tuple[str, str, str]:
    """(full key, prefix, hash). The key is `vk_<prefix>_<secret>`; the prefix finds the row."""
    prefix = secrets.token_hex(4)
    key = f"vk_{prefix}_{secrets.token_urlsafe(30)}"
    return key, prefix, _hash(key)


def service_user() -> User:
    """The identity API writes are recorded under. It is an inactive Admin-role account with no
    password: it can never sign in, and it is not counted as 'the last admin'."""
    user, made = User.objects.get_or_create(
        username=SERVICE_USERNAME,
        defaults={"name": "API key (service)", "role": Role.ADMIN, "is_active": False,
                  "must_change_password": False})
    if made:
        user.set_unusable_password()
        user.save(update_fields=["password"])
    return user


class ApiKeyAuthentication(BaseAuthentication):
    """`Authorization: Api-Key vk_...` or `X-API-Key: vk_...`. A revoked key stops at once."""

    def authenticate_header(self, request: Request) -> Any:
        return "Api-Key"

    def authenticate(self, request: Request) -> Any:
        header = get_authorization_header(request).decode()
        key = header[8:] if header.startswith("Api-Key ") else request.headers.get("X-API-Key")
        if not key:
            return None
        parts = key.split("_")
        row = ApiKey.objects.filter(prefix=parts[1]).first() if len(parts) >= 3 else None
        if row is None or not secrets.compare_digest(row.key_hash, _hash(key)):
            raise AuthenticationFailed("Invalid API key.")
        if row.revoked_at is not None:
            raise AuthenticationFailed("This API key was revoked.")
        ApiKey.objects.filter(pk=row.pk).update(last_used_at=timezone.now())
        return service_user(), row
