import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


class Role(models.TextChoices):
    EXPERT = "expert"
    OPS = "ops"
    ADMIN = "admin"


class Theme(models.TextChoices):
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"       # follow the device


class UserManager(BaseUserManager):
    def get_queryset(self):
        # the picture bytes are only ever read by the picture endpoint, never by ordinary queries
        return super().get_queryset().defer("avatar")

    def create_user(self, username, password, role, **extra):
        user: User = self.model(username=username, role=role, **extra)  # type: ignore[assignment]
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password, **extra):
        extra.setdefault("must_change_password", False)
        return self.create_user(username, password, role=Role.ADMIN, **extra)


class User(AbstractBaseUser):
    username = models.CharField(max_length=150, unique=True)
    name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    role = models.CharField(max_length=10, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    must_change_password = models.BooleanField(default=True)
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    phone = models.CharField(max_length=20, blank=True)      # set only by an Admin
    theme = models.CharField(max_length=10, choices=Theme.choices, default=Theme.LIGHT)
    # the person's picture: one 256 px square JPEG kept in the database (about 15 KB), so there
    # are no files to clean up; avatar_version changes with every change (cache busting, ETag)
    avatar = models.BinaryField(null=True, blank=True, editable=False)
    has_avatar = models.BooleanField(default=False)
    avatar_version = models.PositiveIntegerField(default=0)
    # Ops mute switches {"submitted": false, ...}; a missing key means on (see apps/notify)
    notify_prefs = models.JSONField(default=dict, blank=True)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["name"]
    objects = UserManager()

    class Meta:
        constraints = [models.UniqueConstraint(Lower("username"), name="user_username_ci_unique")]


class Device(models.Model):
    """A registered mobile device. Web sessions are not devices."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="devices")
    name = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    revoked_at = models.DateTimeField(null=True, blank=True)
    # what the phone last said it still holds: {"drafts": n, "files": n}; null = never reported
    unsynced = models.JSONField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    push_token = models.CharField(max_length=4096, blank=True)   # Firebase token; "" = none
    push_token_at = models.DateTimeField(null=True, blank=True)  # when this device last sent it

    def holds_work(self) -> bool:
        """True when this phone may still hold answers or files the server doesn't have."""
        return self.unsynced is None or any(self.unsynced.values())


class RolePermission(models.Model):
    """One grant: this role may do this action, for its own items or for all. The Admin role is
    never stored (it always has everything); see apps/accounts/catalog.py for the catalog."""

    role = models.CharField(max_length=10, choices=Role.choices)
    permission = models.CharField(max_length=64)
    scope = models.CharField(max_length=3, choices=[("all", "all"), ("own", "own")])

    class Meta:
        constraints = [models.UniqueConstraint(fields=["role", "permission"],
                                               name="one_grant_per_role_permission")]


class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise RuntimeError("AuditLog is append-only")

    def delete(self):
        raise RuntimeError("AuditLog is append-only")


class AuditLog(models.Model):
    """Who changed configuration, when. Rows are never updated or deleted (also enforced by a
    database trigger, see migration 0002)."""

    actor = models.ForeignKey(User, null=True, on_delete=models.PROTECT, related_name="+")
    action = models.CharField(max_length=64, db_index=True)
    target_type = models.CharField(max_length=64)
    target_id = models.CharField(max_length=64)
    summary = models.TextField()
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    objects = AppendOnlyQuerySet.as_manager()

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("AuditLog is append-only")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("AuditLog is append-only")
