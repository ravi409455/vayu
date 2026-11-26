#!/usr/bin/env bash
# Dump the database, encrypt it, put it in the backups bucket: infra/backup.sh [label]
# label: "nightly" (the timer, the default) or e.g. "predeploy-abc1234" (deploy.sh).
#
# Encrypted with the LOCKING half of the backup key (BACKUP_PUBLIC_KEY, tool: age): this server can
# make backups but cannot read them. The unlocking half lives in Phase only.
# The bucket keeps every backup for 30 days whatever anyone does (bucket lock) and deletes it
# after 35 (lifecycle rule). Only the nightly run pings the uptime checker: no ping, Slack alert.
# shellcheck source=infra/lib.sh
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

LABEL=${1:-nightly}
[[ "$LABEL" =~ ^[a-z0-9-]+$ ]] || die "label: lower-case letters, digits and - only"
KEY=$(envval BACKUP_PUBLIC_KEY)
[[ "$KEY" == age1* ]] || die "BACKUP_PUBLIC_KEY (age1...) is not set"

mkdir -p backups
NAME="$(date -u +%Y-%m-%dT%H%MZ)-$LABEL.dump.age"
trap 'rm -f "backups/$NAME"' EXIT

# custom format: compressed, and pg_restore can pick tables out of it
pg pg_dump --format=custom --no-owner --no-privileges | age -r "$KEY" > "backups/$NAME"
[[ $(stat -c %s "backups/$NAME") -gt 1000 ]] || die "the dump is suspiciously small"
s3 cp --only-show-errors "$NAME" "s3://$(envval BACKUP_BUCKET)/$(envval BACKUP_PREFIX)/$NAME"
echo "backup: $(envval BACKUP_PREFIX)/$NAME"

HB=$(envval BACKUP_HEARTBEAT_URL)
if [[ "$LABEL" == nightly && -n "$HB" ]]; then curl -fsS --max-time 10 "$HB" >/dev/null || true; fi
