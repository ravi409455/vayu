"""Sign-in rules: password checks, the lockout after five wrong tries, and one signed-in phone per
person."""

import logging
from typing import Any
from uuid import UUID

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
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


def revoke_devices(user: User, keep: str | None = None) -> int:
    """Sign out every phone of this person (but `keep`) and accept the loss of what they hold:
    a phone that signed itself out holding work stops blocking a new one too. Returns how many
    phones that touched."""
    now = timezone.now()
    phones = Device.objects.filter(user=user)
    if keep is not None:
        phones = phones.exclude(pk=keep)
    count = phones.filter(revoked_at__isnull=True).update(revoked_at=now, push_token="")
    count += phones.filter(held_after_sign_out_at__isnull=False).update(held_after_sign_out_at=None)
    if count:
        log.event("auth.device_revoked", user_id=user.pk, count=count)
    return count


def sign_out_device(user: User, device_id: str, counts: dict[str, int] | None) -> None:
    """The phone signs itself out. With unsent work (`counts` above 0) it keeps holding that work:
    the device is still revoked (its tokens die) but keeps refusing another phone."""
    now = timezone.now()
    changes: dict[str, Any] = {"revoked_at": now, "push_token": ""}
    held = counts if counts is not None and any(counts.values()) else None
    if counts is not None:
        changes["unsynced"] = counts
    if held:
        changes["held_after_sign_out_at"] = now
    if Device.objects.filter(pk=device_id, user=user, revoked_at__isnull=True).update(**changes):
        log.event("auth.device_revoked", user=user, count=1)
        if held:
            log.event("auth.signed_out_holding_work", user=user, **held)


def phone_state(user: User) -> dict[str, Any]:
    """What the person's phones last said they still hold: signed-in phones, and phones that
    signed out still holding work. unknown: a signed-in phone never reported."""
    devices = list(Device.objects.filter(user=user, revoked_at__isnull=True))
    held = list(Device.objects.filter(user=user, held_after_sign_out_at__isnull=False))
    reported = [d.unsynced for d in devices + held if d.unsynced is not None]
    seen = [d.last_seen_at for d in devices if d.last_seen_at]
    return {"devices": len(devices),
            "drafts": sum(int(u.get("drafts", 0) or 0) for u in reported),
            "files": sum(int(u.get("files", 0) or 0) for u in reported),
            "unknown": any(d.unsynced is None for d in devices),
            "signed_out_holding": len(held),
            "last_seen_at": max(seen) if seen else None}


def _phones_holding_work(user: User) -> list[Device]:
    """Signed-in phones, and phones that signed out holding work, that may hold unsent work."""
    phones = Device.objects.select_for_update().filter(user=user).filter(
        Q(revoked_at__isnull=True) | Q(held_after_sign_out_at__isnull=False))
    return [d for d in phones if d.holds_work()]


def register_device_and_tokens(user: User, device_name: str,
                               install_id: UUID | None = None) -> dict[str, Any]:
    """A new phone replaces the old one, unless the old one may still hold work that hasn't
    reached the server (then the person syncs it first, or someone allowed to sign it out does).
    The same install of the app is let back in: it takes its own kept work over."""
    with transaction.atomic():
        holding = _phones_holding_work(user)
        mine = [d for d in holding if install_id is not None and d.install_id == install_id]
        busy = next((d for d in holding if d not in mine), None)
        if busy is not None:
            counts = busy.unsynced or {}
            raise CodedError("DEVICE_HAS_UNSYNCED_DATA",
                             "Your other phone still has work that hasn't been sent. Open the app "
                             "there and let it sync, or ask an Admin to sign that phone out.", 409,
                             drafts=counts.get("drafts"), files=counts.get("files"))
        if mine:
            log.event("auth.device_taken_over", user=user)
        revoke_devices(user)
        device = Device.objects.create(user=user, name=device_name, install_id=install_id)
    log.event("auth.device_registered", user=user, device=str(device.id))
    refresh = RefreshToken.for_user(user)
    refresh["device_id"] = str(device.id)
    return {"access": str(refresh.access_token), "refresh": str(refresh),
            "device_id": str(device.id)}
