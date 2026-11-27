#!/usr/bin/env python3
"""Staging's env file (stdin) → a load-test server's (stdout), for perf/cloud.sh. Never stored on
the laptop: the runner pipes it from the staging server to the test server through this.

    cloud_env.py <host> <server name> [KEY=VALUE ...]   (the size's worker settings)

Only an allowlist comes from staging (KEEP: the file bucket and its key, the Firebase key, the
content rules, database and user names, two app limits). Set here: the address, the server's name
and kind (test), Sentry off (a dummy address; the test counts errors itself), a fresh database
password and secret key. Everything else (backup keys, heartbeats, tester passwords, anything added
to staging later) is left out."""
import os
import re
import secrets
import sys

host, name, extra = sys.argv[1], sys.argv[2], sys.argv[3:]
# the test server is addressed by its IP: Caddy then makes its own certificate (no public CA, no
# DNS; the load script skips the certificate check), and the TLS work on the server is the same
if not re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", host) or not name.startswith("lt-"):
    sys.exit("cloud_env: host must be an IPv4 address and the name lt-*")

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

# an allowlist: only these come from staging; everything else is set below or left out (a new
# staging setting never reaches a throwaway by accident)
KEEP = {"S3_BUCKET", "S3_ENDPOINT_URL", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY", "S3_REGION",
        "FIREBASE_JSON", "FIREBASE_CREDENTIALS_FILE", "CSP_HEADER", "DB_NAME", "DB_USER",
        "MIN_APP_VERSION", "STUCK_UPLOAD_HOURS"}
env = {k: v for k, v in env.items() if k in KEEP}
env.update({
    "VAYU_SERVER_KIND": "test", "VAYU_SERVER_NAME": name,
    "APP_HOST": host, "ALLOWED_HOSTS": host, "CSRF_TRUSTED_ORIGINS": f"https://{host}",
    "PUBLIC_BASE_URL": f"https://{host}", "VERIFY_BASE_URL": f"https://{host}/report/verify",
    "SENTRY_DSN": "https://00000000000000000000000000000000@127.0.0.1:9/0",
    "SENTRY_ENVIRONMENT": "loadtest",
    "DB_HOST": "postgres", "DB_PORT": "5432", "DB_SSLMODE": "prefer",
    "DB_PASSWORD": secrets.token_urlsafe(24), "DJANGO_SECRET_KEY": secrets.token_urlsafe(50),
    "PDF_CONCURRENCY": "1",
    "R2_CALL_LOG": "1",            # each R2 call's own time in the logs (perf/report.py: R2 calls)
})
# run D (perf/cloud.sh dbcheck): a temporary managed database instead of Postgres on the server;
# its details come through the environment (never a command line): "host port user password db"
if os.environ.get("LT_DB"):
    db_host, db_port, db_user, db_password, db_name = os.environ["LT_DB"].split()
    env.update({"DB_HOST": db_host, "DB_PORT": db_port, "DB_USER": db_user,
                "DB_PASSWORD": db_password, "DB_NAME": db_name, "DB_SSLMODE": "require"})
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
