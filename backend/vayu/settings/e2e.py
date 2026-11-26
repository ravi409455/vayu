"""Settings for browser (Playwright) tests: a real server, a real database, an in-process-free S3
(moto server) and Celery running inline. Never used outside tests."""
import os

os.environ.setdefault("DJANGO_SECRET_KEY", "e2e-secret-key-not-for-prod-0123456789")
os.environ.setdefault("DB_NAME", "vayu_e2e")
os.environ.setdefault("DB_USER", "vayu")
os.environ.setdefault("DB_PASSWORD", "vayu")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("S3_BUCKET", "vayu-e2e")
os.environ.setdefault("S3_ENDPOINT_URL", "http://localhost:5055")
os.environ.setdefault("S3_ACCESS_KEY_ID", "test")
os.environ.setdefault("S3_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_REGION", "us-east-1")

from .base import *  # noqa: E402,F401,F403

DEBUG = False
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = False
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
REST_FRAMEWORK = {**REST_FRAMEWORK,  # noqa: F405
                  "DEFAULT_THROTTLE_RATES": {"login": "100000/min", "public": "100000/min",
                                           "avatar": "100000/min"}}
WEBHOOK_ALLOW_HTTP = True
WEBHOOK_ALLOW_PRIVATE = True          # the test receiver listens on localhost
WEB = os.environ.get("E2E_WEB", "http://localhost:5199")   # the Vite dev server in front of the API
PUBLIC_BASE_URL = WEB
VERIFY_BASE_URL = f"{WEB}/report/verify"
CSRF_TRUSTED_ORIGINS = [WEB]
SERVER_KIND, SERVER_NAME = "local", "local"     # test data may wipe this one
