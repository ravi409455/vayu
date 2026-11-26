"""Sign-in rules: password checks, the lockout after five wrong tries, and one signed-in phone per
person."""

import logging
from typing import Any

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core import log
from apps.core.errors import CodedError

from .models import Device, User


def validate_new_password(password: str, username: str) -> None:
    if password.lower() == username.lower():
        raise ValidationError({"password": "Must not be the same as the username."})
    try:
        validate_password(password)  # min length + common-password list (settings)
    except DjangoValidationError as e:
        raise ValidationError({"password": list(e.messages)}) from e


def _failures_key(username: str, ip: str, user: Any) -> str:
    # the password's hash is part of it: a password reset by the Admin ends the lock
    stamp = user.password[-12:] if user is not None else ""
    return f"login-failures:{username.strip().lower()}:{ip}:{stamp}"


ACCOUNT_ALERT_AFTER = 50          # wrong tries on one account from any addresses, in an hour


def _count_account_failures(user: Any) -> None:
    """Guessing spread over many addresses never locks (nobody can lock a colleague out), but it
    raises one alert (error log, so Sentry sees it) when one account collects many wrong tries."""
    from django.core.cache import cache

    if user is None:
        return
    key = f"login-failures-account:{user.pk}"
    cache.add(key, 0, 3600)
    if cache.incr(key) == ACCOUNT_ALERT_AFTER:
        log.event("auth.many_failures", level=logging.ERROR, user_id=user.pk,
                  tries=ACCOUNT_ALERT_AFTER)


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
    # the typed username is never logged (it can be a mistyped password): the id, or "unknown user"
    who = user.pk if user is not None else "unknown user"
    if failures >= settings.LOCKOUT_MAX_FAILURES:
        log.event("auth.sign_in_locked", level=logging.WARNING, user_id=who, ip=ip)
        raise fail
    if user is None:
        make_password(password)        # the same hashing time as a real user (no timing hint)
    if user is None or not user.check_password(password) or not user.is_active:
        # ponytail: get + set is not atomic; two tries in the same instant may count once
        cache.set(key, failures + 1, settings.LOCKOUT_MINUTES * 60)
        reason = "no_user" if user is None else "inactive" if not user.is_active \
            else "bad_password"
        log.event("auth.sign_in_failed", level=logging.WARNING, user_id=who, ip=ip, reason=reason)
        if failures + 1 >= settings.LOCKOUT_MAX_FAILURES:
            log.event("auth.locked_out", level=logging.WARNING, user_id=who, ip=ip)
        _count_account_failures(user)
        raise fail
    cache.delete(key)
    log.event("auth.sign_in", user=user, ip=ip)
    # last sign-in, for the Users list (web and phone alike)
    type(user).objects.filter(pk=user.pk).update(last_login=timezone.now())
    return user


def revoke_devices(user: User) -> int:
    count = Device.objects.filter(user=user, revoked_at__isnull=True).update(
        revoked_at=timezone.now(), push_token="")
    if count:
        log.event("auth.device_revoked", user_id=user.pk, count=count)
    return count


def register_device_and_tokens(user: User, device_name: str) -> dict[str, Any]:
    """A new phone replaces the old one, unless the old one may still hold work that hasn't
    reached the server (then the person syncs it first, or someone allowed to sign it out does)."""
    with transaction.atomic():
        busy = next((d for d in Device.objects.select_for_update().filter(
            user=user, revoked_at__isnull=True) if d.holds_work()), None)
        if busy is not None:
            counts = busy.unsynced or {}
            raise CodedError("DEVICE_HAS_UNSYNCED_DATA",
                             "Your other phone still has work that hasn't been sent. Open the app "
                             "there and let it sync, or ask an Admin to sign that phone out.", 409,
                             drafts=counts.get("drafts"), files=counts.get("files"))
        revoke_devices(user)
        device = Device.objects.create(user=user, name=device_name)
    log.event("auth.device_registered", user=user, device=str(device.id))
    refresh = RefreshToken.for_user(user)
    refresh["device_id"] = str(device.id)
    return {"access": str(refresh.access_token), "refresh": str(refresh),
            "device_id": str(device.id)}
