"""Settings for running the whole stack on a laptop for manual review: a real Postgres and Redis,
a real Celery worker and beat, an S3-compatible file store, and the Vite dev server in front.
Nothing here is for production."""
import os

os.environ.setdefault("DJANGO_SECRET_KEY", "local-secret-key-not-for-prod-0123456789")
os.environ.setdefault("DB_NAME", "vayu_local")
os.environ.setdefault("DB_USER", "vayu")
os.environ.setdefault("DB_PASSWORD", "vayu")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("S3_BUCKET", "vayu-local")
os.environ.setdefault("S3_ENDPOINT_URL", "http://localhost:9000")
os.environ.setdefault("S3_ACCESS_KEY_ID", "vayulocal")
os.environ.setdefault("S3_SECRET_ACCESS_KEY", "vayulocal-secret")
os.environ.setdefault("S3_REGION", "us-east-1")

from .base import *  # noqa: E402,F401,F403

DEBUG = False
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
# the Vite dev server in front of the API, and a second one (5174) when two run side by side
CSRF_TRUSTED_ORIGINS = ["http://localhost:5173", "http://localhost:5174"]
PUBLIC_BASE_URL = "http://localhost:5173"
VERIFY_BASE_URL = "http://localhost:5173/report/verify"
WEBHOOK_ALLOW_HTTP = True                             # so a receiver on this laptop can be tried
WEBHOOK_ALLOW_PRIVATE = True
PASSWORD_HASHERS = ["django.contrib.auth.hashers.PBKDF2PasswordHasher"]
SERVER_KIND, SERVER_NAME = "local", "local"     # test data may wipe this one
