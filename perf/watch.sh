#!/usr/bin/env bash
# Watch a load test while it runs, refreshed every 10 s (Ctrl+C stops watching, never the test).
#
#   perf/watch.sh            the newest run: a cloud one (perf/cloud.sh rehearse | all | dbcheck)
#                            or a local one (perf/local/run.sh)
#   perf/watch.sh <folder>   that run's results folder
set -uo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
dir=${1:-$(ls -td "$ROOT"/perf/results/*/ "$ROOT"/perf/local/results/*/ 2>/dev/null | head -1)}
[[ -n "$dir" && -d "$dir" ]] || { echo "no load-test run yet (perf/results, perf/local/results)"; exit 1; }
dir=${dir%/}

case "$dir" in */perf/local/results/*) exec python3 "$ROOT/perf/local/watch.py" "$dir/" ;; esac

while true; do
  out="Cloud load test: $(basename "$dir")    $(date +%H:%M:%S)"$'\n'
  if [[ -f "$dir/OVERVIEW.md" ]]; then
    out+=$'\nFINISHED\n\n'"$(cat "$dir/OVERVIEW.md")"
  else
    out+=$'\nServers running (tag vayu-loadtest):\n'
    out+="$(doctl compute droplet list --tag-name vayu-loadtest --format Name,VCPUs,Memory,Status --no-header 2>/dev/null \
            | sed 's/^/  /')"$'\n'
    out+="Spent so far: \$$(python3 -c "import json; print(round(json.load(open('$ROOT/perf/.cloud/state.json'))['spent'], 2))" 2>/dev/null)"$'\n'
    for log in "$dir"/*.log; do
      [[ -f "$log" ]] || { out+=$'\n(the servers are still being made)\n'; break; }
      out+=$'\n'"== $(basename "$log" .log)"$'\n'"$(grep -v '^\s*$' "$log" | tail -4 | cut -c1-120 | sed 's/^/  /')"$'\n'
    done
  fi
  printf '\033[2J\033[H%s\n' "$out"
  [[ -f "$dir/OVERVIEW.md" ]] && exit 0
  sleep 10
done
