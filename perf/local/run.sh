#!/usr/bin/env bash
# The local load test, start to results (docs/plan-load-test.md, "local run").
#   perf/local/run.sh [cpuset] [minutes]        e.g. perf/local/run.sh 0 120  (1 vCPU, 2 hours)
# The clock starts once everyone has signed in; minutes 0-55 are the warm-up (an inspection's files
# take 25 minutes, then Ops review it for 30: only from minute 55 is every kind of work going on at
# once), and the report measures the next 60 minutes.
#   SMOKE=1 perf/local/run.sh 0 6               a quick check of the scripts (tiny data, fast pace)
# Results: perf/local/results/<time>/RESULTS.md. Stop the server after: perf/local/stack.sh down
set -euo pipefail
cd "$(dirname "$0")/../.."
CPUS=${1:-0}; MINUTES=${2:-120}
RUN=perf/local/results/$(date +%Y%m%d-%H%M)-cpu${CPUS//,/_}${SMOKE:+-smoke}
mkdir -p "$RUN"; chmod 700 "$RUN"
S=perf/local/stack.sh
PW=local-loadtest-$(openssl rand -hex 6)

echo "== server, pinned to CPU $CPUS"
$S up "$CPUS"
if ! $S exec python manage.py shell -c "from apps.forms.models import Form; import sys; sys.exit(0 if Form.objects.filter(key='pdi').exists() else 1)" 2>/dev/null; then
  printf 'username,name,role,phone,password\nltadmin,Load Admin,admin,9700000001,%s\n' "$PW" > "$RUN/staff.csv"
  $S cp "$RUN/staff.csv" api:/tmp/staff.csv >/dev/null
  $S exec python manage.py setup_platform --users /tmp/staff.csv | tail -1
  rm -f "$RUN/staff.csv"
fi

echo "== logins, API key, webhooks, history, today's bookings"
if [[ -n "${SMOKE:-}" ]]; then SIZE=(--experts 4 --ops 2 --history-days 1 --per-day 4 --inspected-per-day 2 --today 3)
else SIZE=(--experts 50 --ops 5 --history-days 90 --per-day 200 --inspected-per-day 100 --today 20); fi
$S exec python manage.py loadtest_prepare --password "$PW" --receiver http://receiver.lvh.me:9300 \
  --out /tmp/lt.json "${SIZE[@]}" 2>&1 | grep -v '"levelname"' | tail -2
$S cp api:/tmp/lt.json "$RUN/lt.json" >/dev/null; chmod 600 "$RUN/lt.json"

echo "== run: $MINUTES minutes"
python3 perf/receiver.py --port 9300 --out "$RUN/webhooks.csv" & RECV=$!
perf/local/sample.sh "$RUN/stats.csv" & SAMPLER=$!
trap 'kill $RECV $SAMPLER 2>/dev/null || true' EXIT
PACE=(); [[ -n "${SMOKE:-}" ]] && PACE=(LT_UPLOAD_MINUTES=1 LT_REVIEW_MINUTES=1)
PHOTOS="${LT_PHOTOS:-$HOME/vayu-loadtest-photos}"   # real car photos, if the folder is there
[[ -d "$PHOTOS" ]] && PACE+=(LT_PHOTOS="$PHOTOS")
env LT_DATA="$RUN/lt.json" LT_OUT="$RUN" LT_TLS_VERIFY=0 ${PACE[@]+"${PACE[@]}"} \
  uv run --quiet --with locust --with pillow locust -f perf/loadtest.py --headless \
  --host https://localhost -u 58 -r 0.3 --run-time "${MINUTES}m" --only-summary > "$RUN/locust.log" 2>&1 || true
sleep 60    # the last files' checks and PDFs

echo "== the server's own records"
ids=$(cut -d, -f2 "$RUN/uploads.csv" 2>/dev/null | sed "s/.*/'&'/" | paste -sd, -)
psql() { docker exec -i vayu-postgres-1 psql -U vayu -d vayu -At -F, "$@"; }
[[ -n "$ids" ]] && psql -c "select id, extract(epoch from verified_at), status from media_mediaasset where id in ($ids)" > "$RUN/verified.csv"
bids=$(awk -F, '$3=="submitted"{print "'\''"$2"'\''"}' "$RUN/inspections.csv" 2>/dev/null | paste -sd, -)
[[ -n "$bids" ]] && psql -c "select id, stage from bookings_booking where id in ($bids)" > "$RUN/stages.csv"
rm -f "$RUN/lt.json"     # holds the test logins' password and the API key

if [[ -n "${SMOKE:-}" ]]; then FROM=0; LEN=$MINUTES; else FROM=55; LEN=$(( MINUTES - 60 )); fi
NCPU=$(python3 -c "import sys; print(sum(len(range(int(a), int(b or a) + 1)) for a, _, b in (p.partition('-') for p in sys.argv[1].split(','))))" "$CPUS")
python3 perf/report.py "$RUN" --from-min "$FROM" --minutes "$LEN" --memory-mb 2048 --cpus "$NCPU" > "$RUN/RESULTS.md"
cat "$RUN/RESULTS.md"
