from datetime import timedelta

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


def authenticate(username: str, password: str) -> User:
    """Check credentials with lockout. Failure counters are saved before the error is raised
    (raising inside the transaction would roll them back)."""
    error: CodedError | None = None
    now = timezone.now()
    with transaction.atomic():
        user = User.objects.select_for_update().filter(username__iexact=username).first()
        if user is None:
            error = CodedError("INVALID_CREDENTIALS", "Invalid username or password.", 401)
        elif not user.is_active:
            error = CodedError("ACCOUNT_DISABLED", "This account is disabled.", 403)
        elif user.locked_until and user.locked_until > now:
            error = CodedError("ACCOUNT_LOCKED", "Too many failed attempts. Try again later.", 403)
        elif not user.check_password(password):
            user.failed_attempts += 1
            if user.failed_attempts >= settings.LOCKOUT_MAX_FAILURES:
                user.failed_attempts = 0
                user.locked_until = now + timedelta(minutes=settings.LOCKOUT_MINUTES)
                error = CodedError("ACCOUNT_LOCKED",
                                   "Too many failed attempts. Try again later.", 403)
            else:
                error = CodedError("INVALID_CREDENTIALS", "Invalid username or password.", 401)
            user.save(update_fields=["failed_attempts", "locked_until"])
        elif user.failed_attempts or user.locked_until:
            user.failed_attempts = 0
            user.locked_until = None
            user.save(update_fields=["failed_attempts", "locked_until"])
    if error:
        raise error
    return user  # type: ignore[return-value]


def revoke_devices(user: User) -> int:
    return Device.objects.filter(user=user, revoked_at__isnull=True).update(
        revoked_at=timezone.now())


def register_device_and_tokens(user: User, device_name: str) -> dict:
    """New device replaces the old one (unsynced-data protection arrives with the heartbeat in
    Phase 13)."""
    with transaction.atomic():
        revoke_devices(user)
        device = Device.objects.create(user=user, name=device_name)
    refresh = RefreshToken.for_user(user)
    refresh["device_id"] = str(device.id)
    return {"access": str(refresh.access_token), "refresh": str(refresh),
            "device_id": str(device.id)}
