from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import SENTRY_DSN, env

# Staging uses the same module with different environment variables.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = False  # TLS is terminated by Caddy
# Only Caddy publishes ports (see compose); gunicorn is reachable only on the internal network,
# so X-Forwarded-Proto can only come from Caddy, which overwrites it.
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = [o for o in env("CSRF_TRUSTED_ORIGINS", "").split(",") if o]
if not SENTRY_DSN:
    raise ImproperlyConfigured("SENTRY_DSN is required in production")
# webhook payloads carry absolute links: a localhost default would send dead ones (F-216)
PUBLIC_BASE_URL = env("PUBLIC_BASE_URL")

# Behind Caddy: the client address is the last X-Forwarded-For entry, which Caddy sets
REST_FRAMEWORK = {**REST_FRAMEWORK, "NUM_PROXIES": 1}  # noqa: F405
