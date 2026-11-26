#!/usr/bin/env bash
# What used the server, every 5 minutes (cron of `deploy`, set by bootstrap.sh). DigitalOcean's
# graphs and alerts say WHEN the box was busy; this says WHICH service. One line for the box (load,
# memory, swap, disk) and one per container, in /srv/vayu/logs/resources-<date>.log, 14 days kept.
#   infra/resources.sh            record one sample (what cron runs)
#   infra/resources.sh show [N]   the last N samples (default 3), e.g. right after an alert
set -euo pipefail
DIR=/srv/vayu/logs
mkdir -p "$DIR"

if [[ "${1:-}" == show ]]; then
  # each sample starts with its "host" line: print the last N samples
  cat "$DIR"/resources-*.log 2>/dev/null | awk -v n="${2:-3}" '
    / host / {i++} {line[NR]=$0; s[NR]=i} END {for (k=1; k<=NR; k++) if (s[k] > i-n) print line[k]}'
  exit 0
fi

t=$(date -u +%FT%TZ)
{
  echo "$t host load=$(cut -d' ' -f1-3 /proc/loadavg | tr ' ' ,)" \
    "mem=$(free -m | awk '/Mem:/{print $3 "/" $2 "MB"}') swap=$(free -m | awk '/Swap:/{print $3 "MB"}')" \
    "disk=$(df -h / | awk 'NR==2{print $5}')"
  docker stats --no-stream --format "$t {{.Name}} cpu={{.CPUPerc}} mem={{.MemUsage}}"
} >> "$DIR/resources-$(date -u +%F).log"
find "$DIR" -name 'resources-*.log' -mtime +14 -delete
