#!/usr/bin/env bash
# Restore a backup made by backup.sh.
#   infra/restore.sh                      list the backups
#   infra/restore.sh <name> [--drill]     the monthly drill: load it into a THROWAWAY database and
#                                         print the biggest tables next to the live ones; nothing live changes
#   infra/restore.sh <name> --into-live   disaster only: replace the live database with the backup.
#                                         Stop the app first (runbook); asks you to type the server name.
# You paste the backup UNLOCKING key (AGE-SECRET-KEY-..., from Bitwarden) when asked; it is never stored.
# shellcheck source=infra/lib.sh
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

PREFIX="s3://$(envval BACKUP_BUCKET)/$(envval BACKUP_PREFIX)/"
if [[ $# -eq 0 ]]; then s3 ls "$PREFIX"; exit 0; fi
NAME=$1
MODE=${2:---drill}
[[ "$NAME" =~ ^[A-Za-z0-9:._-]+\.dump\.age$ ]] || die "give a name from the list"
[[ "$MODE" == --drill || "$MODE" == --into-live ]] || die "second argument: --drill or --into-live"

if [[ "$MODE" == --into-live ]]; then
  SERVER=$(envval VAYU_SERVER_NAME)
  read -rp "This REPLACES the live database of $SERVER. Type $SERVER to go on: " typed
  [[ "$typed" == "$SERVER" ]] || die "stopped"
fi

read -rsp "Paste the backup unlocking key: " SECRET || die "no key given"; echo
[[ "$SECRET" == AGE-SECRET-KEY-* ]] || die "that is not a backup unlocking key (AGE-SECRET-KEY-...)"

mkdir -p backups
trap 'rm -f backups/restore.dump backups/restore.dump.age' EXIT
s3 cp --only-show-errors "$PREFIX$NAME" restore.dump.age < /dev/null
age -d -i <(printf '%s\n' "$SECRET") -o backups/restore.dump backups/restore.dump.age
unset SECRET

SIZES="ANALYZE; SELECT relname AS table, n_live_tup AS rows FROM pg_stat_user_tables ORDER BY n_live_tup DESC LIMIT 12;"
START=$(date +%s)

if [[ "$MODE" == --into-live ]]; then
  pg pg_restore --clean --if-exists --no-owner --no-privileges -d "$(envval DB_NAME)" < backups/restore.dump
  echo "== restored into the live database in $(( $(date +%s) - START ))s. Now:"
  pg psql -c "$SIZES"
  exit 0
fi

# the drill: a throwaway Postgres on this server (customer data never leaves it)
docker rm -f vayu-restore-drill >/dev/null 2>&1 || true
docker run -d --name vayu-restore-drill -e POSTGRES_PASSWORD=drill postgres:16-alpine >/dev/null
trap 'rm -f backups/restore.dump backups/restore.dump.age; docker rm -f vayu-restore-drill >/dev/null 2>&1 || true' EXIT
until docker exec vayu-restore-drill pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done
sleep 2
docker exec -i vayu-restore-drill pg_restore --no-owner --no-privileges -U postgres -d postgres < backups/restore.dump
echo "== restored in $(( $(date +%s) - START ))s. Backup:"
docker exec vayu-restore-drill psql -U postgres -c "$SIZES"
echo "== live now (rows added since the backup are expected):"
pg psql -c "$SIZES"
echo "Write today's date and the time above in docs/runbook-new-server.md (restore drills)."
