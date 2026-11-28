"""Settings shared by every environment, read from environment variables."""
import os
from datetime import timedelta
from pathlib import Path
from typing import Any

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
    "apps.integrations",
    "apps.notify",
    "apps.platform",          # setup, demo and test data: on top of every other app (F-003)
    "drf_spectacular",
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

TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "APP_DIRS": True,
              "OPTIONS": {"context_processors": ["django.template.context_processors.request"]}}]
ROOT_URLCONF = "vayu.urls"
WSGI_APPLICATION = "vayu.wsgi.application"

# typed: the OPTIONS dict mixes value types, and DATABASES["default"]["NAME"] must type-check
DATABASES: dict[str, dict[str, Any]] = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME"),
        "USER": env("DB_USER"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST": env("DB_HOST"),
        "PORT": env("DB_PORT", "5432"),
        # "require" for the managed database in production (it refuses plain connections)
        "OPTIONS": {"sslmode": env("DB_SSLMODE", "prefer")},
        # one connection per request here; production keeps them (prod.py). Never on the
        # development server: it starts a thread per request, so kept connections pile up until
        # Postgres runs out (it hung the browser tests)
        "CONN_MAX_AGE": 0,
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
    "DEFAULT_SCHEMA_CLASS": "apps.platform.schema.Schema",
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.Pages",
    "PAGE_SIZE": 50,
    # abuse limits per client IP (views opt in with throttle_scope); counters live in Redis so
    # every gunicorn worker shares them
    "DEFAULT_THROTTLE_RATES": {"login": "20/min", "refresh": "120/min", "public": "60/min",
                                "avatar": "20/hour"},
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
VERIFY_BASE_URL = env("VERIFY_BASE_URL", "https://vayu.carcid.in/report/verify")
# one queue per kind of work (F-084): a pile of ZIPs never holds up upload checks or webhooks
CELERY_TASK_ROUTES = {
    "apps.reports.tasks.render_report": {"queue": "pdf"},
    "apps.media.tasks.verify_asset": {"queue": "uploads"},
    "apps.media.zips.build_zip": {"queue": "zips"},
    "apps.media.tasks.purge_expired": {"queue": "purge"},
    "apps.media.tasks.delete_files": {"queue": "purge"},
    "apps.integrations.tasks.*": {"queue": "notify"},
    "apps.bookings.tasks.*": {"queue": "notify"},
    "apps.notify.tasks.*": {"queue": "notify"},
}
# no task runs for ever (F-210): a hung R2 stream is stopped; the PDF render has its own
CELERY_TASK_SOFT_TIME_LIMIT, CELERY_TASK_TIME_LIMIT = 900, 960
CELERY_TASK_ACKS_LATE = True                 # a restart puts the running task back
CELERY_WORKER_HIJACK_ROOT_LOGGER = False     # workers log JSON like the API (F-212)
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
STUCK_UPLOAD_HOURS = int(env("STUCK_UPLOAD_HOURS", "6"))

# What kind of server this is. Test data (seed_test_data) wipes the server, so it runs only where
# this says "local" or "test"; anything else, the default included, counts as production.
SERVER_KIND = env("VAYU_SERVER_KIND", "production")
SERVER_NAME = env("VAYU_SERVER_NAME", "")      # typed back to confirm a wipe

# Webhooks
PUBLIC_BASE_URL = env("PUBLIC_BASE_URL", "http://localhost:8000")   # absolute links in payloads
WEBHOOK_TIMEOUT = 10
WEBHOOK_RETRY_SECONDS = [60, 300, 1800, 7200, 21600, 43200]     # 1m 5m 30m 2h 6h 12h
WEBHOOK_ALLOW_HTTP = False         # https only; dev/test may allow plain http
WEBHOOK_ALLOW_PRIVATE = False      # never call private/loopback/link-local addresses
WEBHOOK_LINK_DAYS = 7
CELERY_BEAT_SCHEDULE = {
    "retry-webhooks": {"task": "apps.integrations.tasks.retry_due", "schedule": 60.0},
    "checkin-due": {"task": "apps.bookings.tasks.checkin_due", "schedule": 60.0},
    "sweep-reports": {"task": "apps.reports.tasks.sweep_reports", "schedule": 300.0},
    "purge-media": {"task": "apps.media.tasks.purge_expired", "schedule": 3600.0},
    "stuck-uploads": {"task": "apps.media.tasks.flag_stuck_uploads", "schedule": 3600.0},
    "recheck-uploads": {"task": "apps.media.tasks.recheck_uploads", "schedule": 900.0},
    "late-starts": {"task": "apps.notify.tasks.late_starts", "schedule": 300.0},
    "heartbeat": {"task": "apps.platform.tasks.heartbeat", "schedule": 300.0},
}
# The uptime checker's "workers alive" address: beat queues the heartbeat, a worker pings it. If
# beat, Redis or the workers stop, the pings stop and the checker alerts. Empty = off.
WORKERS_HEARTBEAT_URL = env("WORKERS_HEARTBEAT_URL", "")

CELERY_BROKER_URL = REDIS_URL
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_DEFAULT_QUEUE = "default"

# Push: path to the Firebase service-account JSON (kept out of git); empty = no pushes
FCM_CREDENTIALS = env("FIREBASE_CREDENTIALS_FILE", "")

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
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s %(task_id)s",
        }
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json",
                             "filters": ["request_id"]}},
    "root": {"handlers": ["console"], "level": "INFO"},
    # about 8 INFO lines per PDF otherwise (F-231)
    "loggers": {"weasyprint": {"level": "WARNING"}, "weasyprint.progress": {"level": "WARNING"}},
}

SENTRY_DSN = env("SENTRY_DSN", "")
if SENTRY_DSN:
    import sentry_sdk

    from vayu.sentry_scrub import OPTIONS

    sentry_sdk.init(dsn=SENTRY_DSN, **OPTIONS)

# ~200 "could not derive the type" warnings on every check and migrate until the schema gets
# real types (R-10); they hide the warnings that matter (F-231)
SILENCED_SYSTEM_CHECKS = ["drf_spectacular.W002"]

SPECTACULAR_SETTINGS = {"TITLE": "Vayu API", "VERSION": "1.0.0", "SERVE_INCLUDE_SCHEMA": False,
                        "SCHEMA_PATH_PREFIX": "/api/v1",
                        "POSTPROCESSING_HOOKS": [
                            "drf_spectacular.hooks.postprocess_schema_enums",
                            "apps.platform.error_codes.add_error_responses"]}
