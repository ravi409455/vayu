from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.db import models


class Role(models.TextChoices):
    EXPERT = "expert"
    OPS = "ops"
    ADMIN = "admin"


class UserManager(BaseUserManager):
    pass  # filled in Task 1.3


class User(AbstractBaseUser):
    username = models.CharField(max_length=150, unique=True)
    role = models.CharField(max_length=10, choices=Role.choices)

    USERNAME_FIELD = "username"
    objects = UserManager()
