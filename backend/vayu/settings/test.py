import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret-key-not-for-prod-0123456789")
os.environ.setdefault("DB_NAME", "vayu")
os.environ.setdefault("DB_USER", "vayu")
os.environ.setdefault("DB_PASSWORD", "vayu")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("S3_BUCKET", "vayu-test")
os.environ.setdefault("S3_ACCESS_KEY_ID", "test")
os.environ.setdefault("S3_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_REGION", "us-east-1")

from .base import *  # noqa: E402,F401,F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # fast tests only

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
PDF_RETRY_DELAY = 0
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
REST_FRAMEWORK = {**REST_FRAMEWORK,  # noqa: F405
                  "DEFAULT_THROTTLE_RATES": {"login": "100000/min", "public": "100000/min"}}
WEBHOOK_ALLOW_HTTP = True
WEBHOOK_RETRY_SECONDS = [60, 300, 1800, 7200, 21600, 43200]
