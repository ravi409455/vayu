from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import SENTRY_DSN, env

# Staging uses the same module with different environment variables.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = False  # TLS is terminated by Caddy
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = [o for o in env("CSRF_TRUSTED_ORIGINS", "").split(",") if o]
if not SENTRY_DSN:
    raise ImproperlyConfigured("SENTRY_DSN is required in production")
