import os
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise ImproperlyConfigured(f"Missing required environment variable: {name}")
    return value


SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = [h for h in env("ALLOWED_HOSTS", "localhost").split(",") if h]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "rest_framework",
    "apps.core",
    "apps.accounts",
    "apps.forms",
    "apps.bookings",
    "apps.scoring",
    "apps.media",
    "apps.reports",
]

MIDDLEWARE = [
    "apps.core.middleware.RequestIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
X_FRAME_OPTIONS = "DENY"

ROOT_URLCONF = "vayu.urls"
WSGI_APPLICATION = "vayu.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME"),
        "USER": env("DB_USER"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST": env("DB_HOST"),
        "PORT": env("DB_PORT", "5432"),
    }
}
REDIS_URL = env("REDIS_URL")
CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache",
                      "LOCATION": REDIS_URL}}

AUTH_USER_MODEL = "accounts.User"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
TIME_ZONE = "Asia/Kolkata"
USE_TZ = True

REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "apps.core.exceptions.handler",
    "DEFAULT_PARSER_CLASSES": [
        "apps.core.exceptions.ObjectJSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.accounts.authentication.DeviceJWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    # abuse limits per client IP (views opt in with throttle_scope); counters live in Redis so
    # every gunicorn worker shares them
    "DEFAULT_THROTTLE_RATES": {"login": "20/min", "public": "60/min"},
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
        "apps.accounts.permissions.PasswordChangeNotRequired",
    ],
}
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=60),
}

# Object storage (Cloudflare R2 in production, any S3 API in dev). Browsers and phones upload
# straight to it with pre-signed URLs; the API only signs and verifies.
S3_BUCKET = env("S3_BUCKET")
S3_ENDPOINT_URL = env("S3_ENDPOINT_URL", "")
S3_ACCESS_KEY_ID = env("S3_ACCESS_KEY_ID")
S3_SECRET_ACCESS_KEY = env("S3_SECRET_ACCESS_KEY")
S3_REGION = env("S3_REGION", "auto")
MEDIA_PART_SIZE = 8 * 1024 * 1024
MEDIA_URL_TTL = 3600           # pre-signed URL lifetime, seconds
ZIP_LINK_DAYS = 7
PDF_RETRY_DELAY = 15           # seconds between render attempts
VERIFY_BASE_URL = env("VERIFY_BASE_URL", "https://verify.carcid.in")
CELERY_TASK_ROUTES = {"apps.reports.tasks.render_report": {"queue": "pdf"}}
STUCK_UPLOAD_HOURS = int(env("STUCK_UPLOAD_HOURS", "6"))

CELERY_BROKER_URL = REDIS_URL
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_DEFAULT_QUEUE = "default"

# Android: apps older than this cannot start new jobs (they can still finish one in progress)
MIN_APP_VERSION = int(env("MIN_APP_VERSION", "0"))

# Auth policy (REQUIREMENTS §2)
LOCKOUT_MAX_FAILURES = 5
LOCKOUT_MINUTES = 15
PASSWORD_MIN_LENGTH = 8
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": PASSWORD_MIN_LENGTH}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]
WEB_SESSION_IDLE_SECONDS = 60 * 60 * 8
SESSION_COOKIE_AGE = WEB_SESSION_IDLE_SECONDS
SESSION_SAVE_EVERY_REQUEST = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_id": {"()": "apps.core.logging.RequestIdFilter"}},
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.json.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s",
        }
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json",
                             "filters": ["request_id"]}},
    "root": {"handlers": ["console"], "level": "INFO"},
}

SENTRY_DSN = env("SENTRY_DSN", "")
if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(dsn=SENTRY_DSN, send_default_pii=False)
