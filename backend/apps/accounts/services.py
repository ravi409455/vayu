
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.errors import CodedError

from .models import Device, User


def validate_new_password(password: str, username: str) -> None:
    if password.lower() == username.lower():
        raise ValidationError({"password": "Must not be the same as the username."})
    try:
        validate_password(password)  # min length + common-password list (settings)
    except DjangoValidationError as e:
        raise ValidationError({"password": list(e.messages)}) from e


def _failures_key(username: str, ip: str, user) -> str:
    # the password's hash is part of it: a password reset by the Admin ends the lock
    stamp = user.password[-12:] if user is not None else ""
    return f"login-failures:{username.strip().lower()}:{ip}:{stamp}"


def authenticate(username: str, password: str, ip: str = "") -> User:
    """Check credentials (F-055). Every failure gets the same answer, so it never says whether a
    username exists, is disabled or is locked. Five wrong tries lock that username from that
    address for LOCKOUT_MINUTES; the same username from another address (many phones share one
    mobile-network IP, so never the whole address) still works."""
    from django.core.cache import cache

    user = User.objects.filter(username__iexact=username).first()
    key = _failures_key(username, ip, user)
    failures = cache.get(key, 0)
    fail = CodedError("INVALID_CREDENTIALS", "Invalid username or password.", 401)
    if failures >= settings.LOCKOUT_MAX_FAILURES:
        raise fail
    if user is None or not user.check_password(password) or not user.is_active:
        # ponytail: get + set is not atomic; two tries in the same instant may count once
        cache.set(key, failures + 1, settings.LOCKOUT_MINUTES * 60)
        raise fail
    cache.delete(key)
    # last sign-in, for the Users list (web and phone alike)
    type(user).objects.filter(pk=user.pk).update(last_login=timezone.now())  # type: ignore[union-attr]
    return user  # type: ignore[return-value]


def revoke_devices(user: User) -> int:
    return Device.objects.filter(user=user, revoked_at__isnull=True).update(
        revoked_at=timezone.now(), push_token="")


def register_device_and_tokens(user: User, device_name: str) -> dict:
    """A new phone replaces the old one, unless the old one may still hold work that hasn't
    reached the server (then the person syncs it first, or Ops sign that phone out)."""
    with transaction.atomic():
        busy = next((d for d in Device.objects.select_for_update().filter(
            user=user, revoked_at__isnull=True) if d.holds_work()), None)
        if busy is not None:
            counts = busy.unsynced or {}
            raise CodedError("DEVICE_HAS_UNSYNCED_DATA",
                             "Your other phone still has work that hasn't been sent. Open the app "
                             "there and let it sync, or ask Ops to sign that phone out.", 409,
                             drafts=counts.get("drafts"), files=counts.get("files"))
        revoke_devices(user)
        device = Device.objects.create(user=user, name=device_name)
    refresh = RefreshToken.for_user(user)
    refresh["device_id"] = str(device.id)
    return {"access": str(refresh.access_token), "refresh": str(refresh),
            "device_id": str(device.id)}
