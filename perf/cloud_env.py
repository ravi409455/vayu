#!/usr/bin/env python3
"""Staging's env file (stdin) → a load-test server's (stdout), for perf/cloud.sh. Never stored on
the laptop: the runner pipes it from the staging server to the test server through this.

    cloud_env.py <host> <server name> [KEY=VALUE ...]   (the size's worker settings)

Kept from staging: the file bucket and its key, the Firebase key, the content rules. Changed: the
address, the server's name and kind (test), Sentry off (a dummy address; the test counts errors
itself), a fresh database password and secret key, no backup keys and no heartbeats (they would
mix the throwaway into staging's backups and alerts)."""
import re
import secrets
import sys

host, name, extra = sys.argv[1], sys.argv[2], sys.argv[3:]
if not re.fullmatch(r"[a-z0-9.-]+\.sslip\.io", host) or not name.startswith("lt-"):
    sys.exit("cloud_env: host must be *.sslip.io and the name lt-*")

env: dict[str, str] = {}
for line in sys.stdin.read().splitlines():
    if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    if value.startswith("'") and value.endswith("'") and len(value) >= 2:
        value = value[1:-1]
    env[key.strip()] = value
for must in ("S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY", "FIREBASE_JSON"):
    if not env.get(must):
        sys.exit(f"cloud_env: staging's settings have no {must}")

for key in list(env):                    # nothing that ties the throwaway to staging's routines
    if key.startswith("BACKUP_") or key.endswith("_HEARTBEAT_URL") or key == "STAGING_TESTER_PASSWORD":
        del env[key]
env.update({
    "VAYU_SERVER_KIND": "test", "VAYU_SERVER_NAME": name,
    "APP_HOST": host, "ALLOWED_HOSTS": host, "CSRF_TRUSTED_ORIGINS": f"https://{host}",
    "PUBLIC_BASE_URL": f"https://{host}", "VERIFY_BASE_URL": f"https://{host}/report/verify",
    "SENTRY_DSN": "https://00000000000000000000000000000000@127.0.0.1:9/0",
    "SENTRY_ENVIRONMENT": "loadtest",
    "DB_HOST": "postgres", "DB_PORT": "5432", "DB_SSLMODE": "prefer",
    "DB_PASSWORD": secrets.token_urlsafe(24), "DJANGO_SECRET_KEY": secrets.token_urlsafe(50),
    "PDF_CONCURRENCY": "1",
})
for kv in extra:
    key, value = kv.split("=", 1)
    env[key] = value

print("# A load-test server's settings (perf/cloud.sh), from staging's with the test's changes.")
for key in sorted(env):
    value = env[key]
    if "\n" in value or "'" in value:
        sys.exit(f"cloud_env: {key} has a line break or a '")
    plain = re.fullmatch(r"[A-Za-z0-9_./:@,+=-]*", value)
    print(f"{key}={value}" if plain else f"{key}='{value}'")
