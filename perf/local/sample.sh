#!/usr/bin/env bash
# The server sampler for a load-test run (perf/local/run.sh here, perf/cloud.sh on a droplet).
#   perf/local/sample.sh <stats.csv>          (stop it with kill)
# Every 5 s, stats.csv: time, container, CPU %, memory (each server container; not the local file
# store: R2 is not on the droplet).
# Every 15 s, host.csv next to it: time, memory total and available (MiB), swap used (MiB), load
# (1 min), disk used %, database size (MiB) and connections, then the length of each work queue
# (default, uploads, notify, pdf, zips, purge). On a laptop the memory, swap and load columns
# are the laptop's (Docker Desktop's VM), so the report uses the container figures there.
out=$1
host="$(dirname "$out")/host.csv"
QUEUES="default uploads notify pdf zips purge"
n=0
while true; do
  now=$(date +%s)
  docker stats --no-stream --format '{{.Name}},{{.CPUPerc}},{{.MemUsage}}' \
    | grep '^vayu-' | grep -v '^vayu-s3-' \
    | sed "s#^#$now,#" >> "$out"
  if (( n % 3 == 0 )); then
    mem=",,"
    if [[ -r /proc/meminfo ]]; then
      mem=$(awk '/^MemTotal:/{t=$2} /^MemAvailable:/{a=$2} /^SwapTotal:/{st=$2} /^SwapFree:/{sf=$2}
                 END {printf "%d,%d,%d", t/1024, a/1024, (st-sf)/1024}' /proc/meminfo)
    fi
    load=$(cut -d' ' -f1 /proc/loadavg 2>/dev/null || true)
    disk=$(df -P / | awk 'NR==2 {gsub("%", "", $5); print $5}')
    db=$(docker exec vayu-postgres-1 psql -U vayu -d vayu -At -F, -c \
      "select pg_database_size('vayu') / 1048576, (select count(*) from pg_stat_activity where datname = 'vayu')" 2>/dev/null || echo ",")
    q=""
    for name in $QUEUES; do
      q="$q,$(docker exec vayu-redis-1 redis-cli llen "$name" 2>/dev/null || true)"
    done
    echo "$now,$mem,$load,$disk,$db$q" >> "$host"
  fi
  n=$((n + 1))
  sleep 5
done
