# shellcheck shell=bash
# Shared by deploy.sh, backup.sh and restore.sh. The server's checkout lives in /srv/vayu with
# exactly one env file: .env.staging or .env.prod. With a .phase file, infra/secrets.sh writes that
# env file from Phase (its PHASE_ENV says which), so it may not exist before the first deploy.
set -euo pipefail

VAYU_DIR=${VAYU_DIR:-/srv/vayu}
cd "$VAYU_DIR"

die() { echo "error: $*" >&2; exit 1; }

if [[ -f .phase ]]; then
  case "$(grep -E '^PHASE_ENV=' .phase | tail -1 | cut -d= -f2-)" in
    Staging) VAYU_ENV_FILE=.env.staging ;;
    Production) VAYU_ENV_FILE=.env.prod ;;
    *) die "PHASE_ENV in .phase must be Staging or Production" ;;
  esac
elif [[ -f .env.prod && -f .env.staging ]]; then die "both .env.prod and .env.staging exist; keep one"
elif [[ -f .env.prod ]]; then VAYU_ENV_FILE=.env.prod
elif [[ -f .env.staging ]]; then VAYU_ENV_FILE=.env.staging
else die "no .phase, .env.prod or .env.staging in $VAYU_DIR"; fi
export VAYU_ENV_FILE

# One value from the env file, without sourcing it (secrets may hold characters bash would read).
# 'quoted' values are taken as they are; otherwise a comment after the value needs a space before
# the #, as Docker Compose reads it.
envval() {
  local v
  v=$(grep -E "^$1=" "$VAYU_ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2-) || true
  if [[ $v == \'* ]]; then v=${v#\'}; printf '%s\n' "${v%%\'*}"
  else printf '%s\n' "$v" | sed -E 's/[[:space:]]+#.*$//; s/[[:space:]]+$//'; fi
}

compose() {
  local profile=()
  [[ "$(envval DB_HOST)" == "postgres" ]] && profile=(--profile local-db)
  FIREBASE_JSON="$(envval FIREBASE_JSON)" docker compose -f infra/docker-compose.prod.yml \
    --env-file "$VAYU_ENV_FILE" ${profile[@]+"${profile[@]}"} "$@"
}

# Secrets reach the helper containers through the environment (-e NAME), never on the command line,
# where `ps` would show them.

# Postgres client tools at the database's own version, on the compose network (staging's "postgres"
# host) or reaching out to the managed database.
pg() {
  PGHOST="$(envval DB_HOST)" PGPORT="$(envval DB_PORT)" PGUSER="$(envval DB_USER)" \
  PGPASSWORD="$(envval DB_PASSWORD)" PGDATABASE="$(envval DB_NAME)" PGSSLMODE="$(envval DB_SSLMODE)" \
    docker run --rm -i --network vayu_default \
      -e PGHOST -e PGPORT -e PGUSER -e PGPASSWORD -e PGDATABASE -e PGSSLMODE postgres:16-alpine "$@"
}

# The backups bucket, with its own key (never the app's). No stdin: it must not swallow input.
s3() {
  AWS_ACCESS_KEY_ID="$(envval BACKUP_ACCESS_KEY_ID)" AWS_SECRET_ACCESS_KEY="$(envval BACKUP_SECRET_ACCESS_KEY)" \
    docker run --rm -v "$VAYU_DIR/backups:/work" -w /work \
      -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY -e AWS_DEFAULT_REGION=auto \
      amazon/aws-cli --endpoint-url "$(envval S3_ENDPOINT_URL)" s3 "$@"
}
