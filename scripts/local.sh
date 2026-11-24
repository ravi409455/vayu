#!/usr/bin/env bash
# Run the whole stack on this laptop for manual review.
#   scripts/local.sh up       start everything (first run also creates the database and demo data)
#   scripts/local.sh down     stop the app (Postgres, Redis and file store containers keep running)
#   scripts/local.sh reset    throw away the local database and files, start fresh with demo data
#   scripts/local.sh status   what is running
# Needs: Docker Desktop, uv, Node 22. Open http://localhost:5173
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN="$ROOT/.local"
export DJANGO_SETTINGS_MODULE=vayu.settings.local
mkdir -p "$RUN"

compose() { docker compose -f "$ROOT/infra/docker-compose.dev.yml" "$@"; }
manage()  { (cd "$ROOT/backend" && uv run python manage.py "$@"); }

wait_port() { # name port
  for _ in $(seq 1 60); do (echo > "/dev/tcp/${3:-127.0.0.1}/$2") 2>/dev/null && return 0; sleep 1; done
  echo "!! $1 did not start on port $2: see $RUN/*.log"; exit 1
}

start_bg() { # name command...
  local name="$1"; shift
  if [ -f "$RUN/$name.pid" ] && kill -0 "$(cat "$RUN/$name.pid")" 2>/dev/null; then echo "  $name already running"; return; fi
  nohup "$@" > "$RUN/$name.log" 2>&1 &
  echo $! > "$RUN/$name.pid"
  echo "  started $name"
}

stop_bg() {
  for f in "$RUN"/*.pid; do
    [ -e "$f" ] || continue
    pid="$(cat "$f")"; name="$(basename "$f" .pid)"
    if kill -0 "$pid" 2>/dev/null; then pkill -P "$pid" 2>/dev/null || true; kill "$pid" 2>/dev/null || true; echo "  stopped $name"; fi
    rm -f "$f"
  done
}

create_db() {
  (cd "$ROOT/backend" && uv run python - <<'PY'
import psycopg
c = psycopg.connect("host=localhost user=vayu password=vayu dbname=postgres", autocommit=True)
if not c.execute("select 1 from pg_database where datname='vayu_local'").fetchone():
    c.execute("create database vayu_local"); print("  created database vayu_local")
PY
  )
}

drop_db() {
  (cd "$ROOT/backend" && uv run python - <<'PY'
import psycopg
c = psycopg.connect("host=localhost user=vayu password=vayu dbname=postgres", autocommit=True)
c.execute("select pg_terminate_backend(pid) from pg_stat_activity where datname='vayu_local'")
c.execute("drop database if exists vayu_local"); print("  dropped database vayu_local")
PY
  )
}

up() {
  echo "Starting Postgres, Redis and the file store..."
  compose up -d postgres redis s3
  wait_port Postgres 5432; wait_port Redis 6379; wait_port Files 9000
  create_db
  echo "Preparing the app..."
  manage migrate -v0
  manage local_bucket
  manage seed_demo --if-empty
  [ -d "$ROOT/web/node_modules" ] || (cd "$ROOT/web" && npm ci)
  echo "Starting the app..."
  cd "$ROOT/backend"
  # pushes: take ONLY the Firebase credential path from .env.local (the file may hold other keys,
  # e.g. real storage, that the local stack must never use)
  if [ -z "${FIREBASE_CREDENTIALS_FILE:-}" ] && [ -f .env.local ]; then
    FIREBASE_CREDENTIALS_FILE="$(sed -n 's/^FIREBASE_CREDENTIALS_FILE=//p' .env.local | tail -1)"
    export FIREBASE_CREDENTIALS_FILE
  fi
  start_bg api uv run python manage.py runserver 8000 --noreload
  start_bg worker uv run celery -A vayu worker -Q default,pdf -c 2 --loglevel=info
  start_bg beat uv run celery -A vayu beat --schedule "$RUN/celerybeat-schedule" --loglevel=info
  cd "$ROOT/web"
  start_bg web npm run dev -- --host localhost
  wait_port API 8000; wait_port Web 5173 localhost
  cat <<MSG

  Vayu is running:  http://localhost:5173
  Sign in (password for all: Vayu-local-1)
    admin    builds forms, users, integrations, API keys
    ops      job board, bookings, reports
    expert   my jobs and the inspection wizard   (expert2 is a second expert)
    newuser  must change the password at first sign in
  Files:   kept in the Docker volume s3-data (the local stand-in for Cloudflare R2)
  API docs http://localhost:5173/api/v1/docs   (sign in as admin first)
  Logs:    $RUN/*.log      Stop: scripts/local.sh down
MSG
}

case "${1:-up}" in
  up) up ;;
  down) echo "Stopping the app..."; stop_bg ;;
  status) for f in "$RUN"/*.pid; do [ -e "$f" ] && { n="$(basename "$f" .pid)"; kill -0 "$(cat "$f")" 2>/dev/null && echo "  $n running" || echo "  $n stopped"; }; done; compose ps ;;
  reset)
    echo "Resetting local data..."; stop_bg
    compose up -d postgres redis s3; wait_port Postgres 5432; wait_port Files 9000
    drop_db; (cd "$ROOT/backend" && uv run python manage.py local_bucket --empty 2>/dev/null || true)
    up ;;
  *) echo "usage: scripts/local.sh up|down|reset|status"; exit 1 ;;
esac
