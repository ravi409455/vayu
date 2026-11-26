#!/usr/bin/env bash
# Fetch this server's settings from Phase (console.phase.dev) and write them where the app reads
# them: /srv/vayu/.env.staging (or .env.prod) and /srv/vayu/secrets/firebase-service-account.json.
# deploy.sh runs it before every deploy, so a secret changed in Phase reaches the server with the
# next deploy (or run this, then deploy the live commit again).
#
# The only secret kept on the server by hand is /srv/vayu/.phase (chmod 600, two lines):
#   PHASE_ENV=Staging                          (or Production: the Phase environment of app vayu)
#   PHASE_SERVICE_TOKEN=pss_service:v2:...     (a service account that sees only that environment)
# No .phase file: nothing is fetched and the env file is used as it is.
# Phase unreachable: the last good env file stays (a warning); with no env file yet, it stops.
set -euo pipefail

VAYU_DIR=${VAYU_DIR:-/srv/vayu}
cd "$VAYU_DIR"
PHASE_CLI=phasehq/cli:2.3.3      # the official image, pinned: update by hand

die() { echo "error: $*" >&2; exit 1; }
conf() { grep -E "^$1=" .phase | tail -1 | cut -d= -f2- || true; }

[[ -f .phase ]] || { echo "no .phase file: settings are not fetched from Phase"; exit 0; }
[[ $(stat -c %a .phase 2>/dev/null || stat -f %Lp .phase) == 600 ]] || die ".phase must be chmod 600"
ENV_NAME=$(conf PHASE_ENV)
case "$ENV_NAME" in
  Staging) OUT=.env.staging ;;
  Production) OUT=.env.prod ;;
  *) die "PHASE_ENV in .phase must be Staging or Production" ;;
esac

# the token goes to the container through the environment, never on a command line (ps shows those)
if ! JSON=$(PHASE_SERVICE_TOKEN=$(conf PHASE_SERVICE_TOKEN) docker run --rm -e PHASE_SERVICE_TOKEN \
    "$PHASE_CLI" secrets export --app vayu --env "$ENV_NAME" --format json 2>/tmp/phase-err); then
  [[ -f $OUT ]] || die "could not fetch from Phase: $(head -c 300 /tmp/phase-err)"
  echo "warning: could not fetch from Phase ($(head -c 200 /tmp/phase-err)); keeping the current $OUT" >&2
  exit 0
fi

mkdir -p secrets && chmod 700 secrets
PHASE_JSON=$JSON python3 -I - "$OUT" <<'PY'
import json, os, re, sys

out = sys.argv[1]
data = json.loads(os.environ["PHASE_JSON"])
if isinstance(data, list):                       # [{"key": .., "value": ..}] in some CLI versions
    data = {d["key"]: d["value"] for d in data}
need = ["VAYU_SERVER_KIND", "VAYU_SERVER_NAME", "APP_HOST", "DJANGO_SECRET_KEY", "DB_HOST",
        "DB_PASSWORD", "SENTRY_DSN", "S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY",
        "FIREBASE_SERVICE_ACCOUNT_JSON"]
missing = [k for k in need if not str(data.get(k, "")).strip()]
if missing:
    sys.exit("error: missing in Phase: " + ", ".join(missing) + " (nothing was changed)")

# the Firebase key is a whole JSON file: written as a file, not an env line
firebase = json.loads(data.pop("FIREBASE_SERVICE_ACCOUNT_JSON"))
fb_path = "secrets/firebase-service-account.json"
with open(fb_path + ".new", "w") as f:
    os.chmod(fb_path + ".new", 0o600)
    json.dump(firebase, f)
data["FIREBASE_JSON"] = os.path.abspath(fb_path)
data.setdefault("FIREBASE_CREDENTIALS_FILE", "/run/secrets/firebase-service-account.json")

lines = ["# Written by infra/secrets.sh from Phase. Do not edit: change it in Phase and redeploy."]
for key in sorted(data):
    value = str(data[key])
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
        sys.exit(f"error: {key!r} is not a valid setting name")
    if "\n" in value or "'" in value:
        sys.exit(f"error: {key} has a line break or a ' (not allowed in a setting)")
    # plain values as they are; anything else in single quotes, which Docker Compose reads literally
    # (no $ expansion, no # comments)
    ok = re.fullmatch(r"[A-Za-z0-9_./:@,+=-]*", value)
    lines.append(f"{key}={value}" if ok else f"{key}='{value}'")
with open(out + ".new", "w") as f:
    os.chmod(out + ".new", 0o600)
    f.write("\n".join(lines) + "\n")
os.replace(fb_path + ".new", fb_path)
os.replace(out + ".new", out)
print(f"settings: {len(data)} values from Phase -> {out}, Firebase key -> {fb_path}")
PY
