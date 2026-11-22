import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret-key-not-for-prod")
os.environ.setdefault("DB_NAME", "inspex")
os.environ.setdefault("DB_USER", "inspex")
os.environ.setdefault("DB_PASSWORD", "inspex")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from .base import *  # noqa: E402,F401,F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # fast tests only
