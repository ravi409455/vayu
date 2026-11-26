# shellcheck shell=bash
# Shared by deploy.sh, backup.sh and restore.sh. The server's checkout lives in /srv/vayu with
# exactly one env file: .env.staging or .env.prod.
set -euo pipefail

VAYU_DIR=${VAYU_DIR:-/srv/vayu}
cd "$VAYU_DIR"

die() { echo "error: $*" >&2; exit 1; }

if [[ -f .env.prod && -f .env.staging ]]; then die "both .env.prod and .env.staging exist; keep one"; fi
if [[ -f .env.prod ]]; then VAYU_ENV_FILE=.env.prod
elif [[ -f .env.staging ]]; then VAYU_ENV_FILE=.env.staging
else die "no .env.prod or .env.staging in $VAYU_DIR"; fi
export VAYU_ENV_FILE

# One value from the env file, without sourcing it (secrets may hold characters bash would read).
# A comment after the value needs a space before the #, as Docker Compose reads it.
envval() {
  grep -E "^$1=" "$VAYU_ENV_FILE" | tail -1 | cut -d= -f2- | sed -E 's/[[:space:]]+#.*$//; s/[[:space:]]+$//' || true
}

compose() {
  local profile=()
  [[ "$(envval DB_HOST)" == "postgres" ]] && profile=(--profile local-db)
  FIREBASE_JSON="$(envval FIREBASE_JSON)" docker compose -f infra/docker-compose.prod.yml \
    --env-file "$VAYU_ENV_FILE" ${profile[@]+"${profile[@]}"} "$@"
}

# Postgres client tools at the database's own version, on the compose network (staging's "postgres"
# host) or reaching out to the managed database.
pg() {
  docker run --rm -i --network vayu_default \
    -e PGHOST="$(envval DB_HOST)" -e PGPORT="$(envval DB_PORT)" -e PGUSER="$(envval DB_USER)" \
    -e PGPASSWORD="$(envval DB_PASSWORD)" -e PGDATABASE="$(envval DB_NAME)" \
    -e PGSSLMODE="$(envval DB_SSLMODE)" postgres:16-alpine "$@"
}

# The backups bucket, with its own key (never the app's). No stdin: it must not swallow input.
s3() {
  docker run --rm -v "$VAYU_DIR/backups:/work" -w /work \
    -e AWS_ACCESS_KEY_ID="$(envval BACKUP_ACCESS_KEY_ID)" \
    -e AWS_SECRET_ACCESS_KEY="$(envval BACKUP_SECRET_ACCESS_KEY)" -e AWS_DEFAULT_REGION=auto \
    amazon/aws-cli --endpoint-url "$(envval S3_ENDPOINT_URL)" s3 "$@"
}
