#!/usr/bin/env bash
# Load tests on throwaway DigitalOcean servers (docs/plan-load-test.md). Runs on the laptop, with
# doctl signed in and the owner's SSH key. Spend is capped (LT_CAP, default $5).
#
#   perf/cloud.sh up <small|mid|base>   create a test server of that size (and the load server)
#   perf/cloud.sh prepare <lowcost|capacity>  cut it off from staging, deploy main, make the data
#   perf/cloud.sh run <lowcost|capacity> run the load script there, collect the results
#   perf/cloud.sh down [all]            delete the test files, destroy the test server ("all": the
#                                       load server too)
#   perf/cloud.sh cost | status         spend so far | what is running
#   perf/cloud.sh lowcost               the whole low-cost test: small, mid, base in turn
#
# Sizes: small = 1 vCPU / 2 GB ($12), mid = 2 vCPU / 2 GB ($18), base = 2 vCPU / 4 GB ($24).
# The load server is 4 vCPU / 8 GB in Bangalore (uploads from a laptop would test its internet).
#
# Safety: the account also holds other projects' servers. This script only ever touches droplets
# it made: named lt-* AND tagged vayu-loadtest, and only ids it wrote in its state file. The test
# server is built fresh (bootstrap.sh + the main images), so it holds none of staging's data; its
# settings are copied from the staging server (server to server, never stored on this laptop) with
# the test's changes: its own address, Sentry off, no backups, no heartbeats, a fresh database.
# Files go to the staging bucket; `down` deletes the test bookings' files by their IDs only.
#
# Cloud runs use the test-only form (owner, 2026-11-27): a PDI copy with an extra last page, so an
# inspection sends 100 photos (150 on 2 of every 9) and 15 videos (`loadtest_prepare --test-form`).
# The local run on the Mac keeps the real PDI form with its 5 videos.
#
# Needs on main: the load-test code (perf/loadtest.py, perf/receiver.py, perf/report.py and
# `manage.py loadtest_prepare`). LT_SRC: a checkout to take perf/ from (default: this one).
# shellcheck disable=SC2016,SC2029  # remote commands: $… must expand on the server, not here
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
SRC=${LT_SRC:-$ROOT}
STATE_DIR="$ROOT/perf/.cloud"
STATE="$STATE_DIR/state.json"
RESULTS="$ROOT/perf/results"
CAP=${LT_CAP:-5}
REGION=blr1
TAG=vayu-loadtest
SSH_KEY_NAME=owner-mac
LOAD_SIZE=s-4vcpu-8gb
STAGING_NAME=vayu-staging
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=30)
mkdir -p "$STATE_DIR" "$RESULTS"
[[ -f "$STATE" ]] || echo '{"spent": 0, "droplets": {}}' > "$STATE"

die() { echo "error: $*" >&2; exit 1; }
say() { echo "== $*"; }
command -v doctl >/dev/null || die "install doctl (brew install doctl) and sign in (doctl auth init)"

# droplet size slug, $/hour, and the app's worker settings for that size
size_info() {
  case "$1" in
    small) echo "s-1vcpu-2gb 0.01786 WEB_CONCURRENCY=2 WORKER_CONCURRENCY=2 ZIP_CONCURRENCY=1 PDF_MEM_LIMIT=1g" ;;
    mid)   echo "s-2vcpu-2gb 0.02679 WEB_CONCURRENCY=3 WORKER_CONCURRENCY=2 ZIP_CONCURRENCY=1 PDF_MEM_LIMIT=1g" ;;
    base)  echo "s-2vcpu-4gb 0.03571 WEB_CONCURRENCY=3 WORKER_CONCURRENCY=3 ZIP_CONCURRENCY=1 PDF_MEM_LIMIT=1500m" ;;
    *) die "size: small, mid or base" ;;
  esac
}
LOAD_PRICE=0.07143

# ---------------------------------------------------------------- state and money

st() {   # st spent | st field <role> <key> | st set <role> <json> | st drop <role>
  python3 - "$STATE" "$@" <<'PY'
import json, sys, time
path, op, args = sys.argv[1], sys.argv[2], sys.argv[3:]
s = json.load(open(path))
hours = lambda d: -(-(time.time() - d["created"]) // 3600)        # billed in whole hours
if op == "spent":                       # spent + running droplets so far
    print(round(s["spent"] + sum(hours(d) * d["price"] for d in s["droplets"].values()), 2))
elif op == "field":
    print(s["droplets"].get(args[0], {}).get(args[1], ""))
elif op == "set":
    s["droplets"][args[0]] = json.loads(args[1])
elif op == "drop":                      # destroyed: its cost moves to "spent"
    d = s["droplets"].pop(args[0], None)
    if d:
        s["spent"] += hours(d) * d["price"]
if op in ("set", "drop"):
    json.dump(s, open(path, "w"), indent=1)
PY
}

spent_now() { st spent; }

check_budget() {   # check_budget <more $ this step may cost>
  python3 -c "import sys; a, b, c = map(float, sys.argv[1:]); sys.exit(0 if a + b <= c else 1)" \
    "$(spent_now)" "$1" "$CAP" \
    || die "this step could take spend past \$$CAP (so far \$$(spent_now)): stopped"
}

ours() {   # ours <id>: true only for a droplet this script made (name lt-*, tag vayu-loadtest)
  doctl compute droplet get "$1" --format Name,Tags --no-header 2>/dev/null \
    | awk -v t="$TAG" '$1 ~ /^lt-/ && index($2, t) { ok = 1 } END { exit !ok }'
}

ip_of() { st field "$1" ip; }
# the throwaways' host keys live in their own file (trusted when first seen, right after we made
# the droplet; secrets go only after verify_ip); staging is reached with the laptop's usual file
on() { local who=$1; shift; ssh "${SSH_OPTS[@]}" -o UserKnownHostsFile="$STATE_DIR/known_hosts" "$who" "$@"; }
on_staging() { local who=$1; shift; ssh "${SSH_OPTS[@]}" "$who" "$@"; }

verify_ip() {   # verify_ip <role>: the address we are about to send secrets to is still our droplet
  local id ip now
  id=$(st field "$1" id); ip=$(ip_of "$1")
  ours "$id" || die "droplet $id is not ours: stopped"
  now=$(doctl compute droplet get "$id" --format PublicIPv4 --no-header)
  [[ "$now" == "$ip" ]] || die "droplet $id is at $now, not $ip: stopped before sending secrets"
}

# ---------------------------------------------------------------- create

make_droplet() {   # make_droplet <role> <name> <size-slug> <price> [user-data file]
  local role=$1 name=$2 slug=$3 price=$4 data=${5:-}
  if [[ -n "$(ip_of "$role")" ]]; then say "$role already up at $(ip_of "$role")"; return; fi
  local key; key=$(doctl compute ssh-key list --format ID,Name --no-header | awk -v k="$SSH_KEY_NAME" '$2 == k {print $1}')
  [[ -n "$key" ]] || die "no SSH key named $SSH_KEY_NAME in DigitalOcean"
  say "creating $name ($slug)"
  # shellcheck disable=SC2054  # "ID,PublicIPv4" is one doctl value
  local args=(--region "$REGION" --size "$slug" --image ubuntu-24-04-x64 --ssh-keys "$key"
              --enable-monitoring --tag-names "$TAG" --wait --format ID,PublicIPv4 --no-header)
  [[ -n "$data" ]] && args+=(--user-data-file "$data")
  local out id ip
  out=$(doctl compute droplet create "$name" "${args[@]}")
  id=$(awk '{print $1}' <<<"$out"); ip=$(awk '{print $2}' <<<"$out")
  st set "$role" "{\"id\": $id, \"name\": \"$name\", \"ip\": \"$ip\", \"size\": \"$slug\", \"price\": $price, \"created\": $(date +%s)}"
  # the web firewall (22, 80, 443) by droplet id, not by tag: the vayu-web tag carries Slack alerts
  local fw; fw=$(doctl compute firewall list --format ID,Name --no-header | awk '$2 == "vayu-web" {print $1}')
  [[ -n "$fw" ]] && doctl compute firewall add-droplets "$fw" --droplet-ids "$id"
  say "$name is $ip; waiting for SSH"
  ssh-keygen -R "$ip" -f "$STATE_DIR/known_hosts" >/dev/null 2>&1 || true
  until on "root@$ip" -o StrictHostKeyChecking=accept-new true 2>/dev/null; do sleep 5; done
}

cmd_up() {
  [[ "${1:-}" =~ ^(small|mid|base)$ ]] || die "up small, up mid or up base"
  local slug price; read -r slug price _ <<<"$(size_info "$1")"
  check_budget "$(python3 -c "print(3 * $price + 3 * $LOAD_PRICE)")"   # a run is ~3 hours
  echo "$1" > "$STATE_DIR/size"
  make_droplet sut "lt-sut-$1" "$slug" "$price"
  local ud="$STATE_DIR/load-user-data.sh"
  printf '#!/bin/sh\ncurl -fsSL https://get.docker.com | sh\n' > "$ud"
  make_droplet load lt-load "$LOAD_SIZE" "$LOAD_PRICE" "$ud"
}

# ---------------------------------------------------------------- prepare the test server

# The load script's interface (the "local load" session's perf/loadtest.py, kept stable):
#   locust -f perf/loadtest.py, env LT_DATA LT_OUT LT_MULT; 58 users per 1× (50 phones, 5 Ops,
#   3 external-system users), signing in at 0.3 a second (the 20-a-minute limit); the measured
#   window of a 90-minute run is minutes 25-85 (perf/report.py --from-min 25 --minutes 60).
# Its clock starts when every user has signed in; the report measures from that clock.
# Capacity: one run per step k (58k users), measured for 15 minutes from its minute 25.
CAP_STEPS=(1 2 3 4 6 8)
signin_min() { python3 -c "import math; print(math.ceil(58 * $1 / 0.3 / 60))"; }
run_min() { echo $(( $(signin_min "$1") + 25 + $2 + 2 )); }   # run_min <k> <measured minutes>

cmd_prepare() {
  local plan=${1:-} size ip host staging sha today
  case "$plan" in
    lowcost) today=14 ;;      # one inspection every 400 s over 90 minutes
    capacity)                 # 9k an hour over each step's run
      today=$(python3 -c "print(sum(round(9 * k * (25 + 15 + 2) / 60) for k in (${CAP_STEPS[*]// /,})) + 10)") ;;
    *) die "prepare lowcost or prepare capacity" ;;
  esac
  [[ -f "$STATE_DIR/size" ]] || die "no test server: up first"
  size=$(cat "$STATE_DIR/size"); ip=$(ip_of sut); [[ -n "$ip" ]] || die "no test server: up first"
  host="lt.$ip.sslip.io"
  staging=$(doctl compute droplet list --tag-name "$STAGING_NAME" --format Name,PublicIPv4 --no-header \
    | awk -v n="$STAGING_NAME" '$1 == n {print $2}')
  [[ -n "$staging" ]] || die "staging is not running: its settings are copied from it"
  sha=$(git -C "$ROOT" ls-remote origin refs/heads/main | awk '{print $1}')

  say "bootstrap (firewall, Docker, deploy user, code); root login is off after it"
  # in the same root session: no nightly backup on a throwaway (it would write into staging's
  # backup folder)
  { cat "$ROOT/infra/bootstrap.sh"; echo 'systemctl disable --now vayu-backup.timer'; } \
    | on "root@$ip" 'bash -s' >/dev/null

  say "settings: an allowlist of staging's, with the test's changes (server to server)"
  verify_ip sut
  local rest sizes; read -r _ _ rest <<<"$(size_info "$size")"; read -ra sizes <<<"$rest"
  on_staging "deploy@$staging" 'cat /srv/vayu/.env.staging' \
    | python3 "$ROOT/perf/cloud_env.py" "$host" "lt-$size" "${sizes[@]}" \
    | on "deploy@$ip" 'umask 077; cat > /srv/vayu/.env.staging'
  # the Firebase key: pushes go to Firebase for real, to fake device tokens (owner's choice);
  # only to this throwaway, destroyed after the run
  on_staging "deploy@$staging" 'cat /srv/vayu/secrets/firebase-service-account.json' \
    | on "deploy@$ip" 'umask 077; mkdir -p /srv/vayu/secrets; cat > /srv/vayu/secrets/firebase-service-account.json'
  on "deploy@$ip" 'rm -f /srv/vayu/.phase'   # never fetch staging's settings from Phase here

  say "deploy main ${sha:0:7}"
  on "deploy@$ip" "bash /srv/vayu/infra/deploy.sh $sha"
  on "deploy@$ip" 'cd /srv/vayu && source infra/lib.sh && VAYU_TAG=$(cat .deployed) compose exec -T api python manage.py help loadtest_prepare >/dev/null' \
    || die "this main has no loadtest_prepare yet: merge the load-test code first"

  say "forms and an Admin (setup_platform), then the test data (loadtest_prepare, $today leads)"
  # random, used only on this throwaway (destroyed after the run)
  local pw admin_pw load
  pw=$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')
  admin_pw=$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')
  load=$(ip_of load)
  on "deploy@$ip" "cd /srv/vayu && source infra/lib.sh && export VAYU_TAG=\$(cat .deployed) &&
    (umask 077; printf 'username,name,role,phone,password\nlt-admin,LT Admin,admin,9700000000,$admin_pw\n' > /tmp/staff.csv) &&
    compose cp /tmp/staff.csv api:/tmp/staff.csv && rm /tmp/staff.csv &&
    compose exec -T api python manage.py setup_platform --users /tmp/staff.csv >/dev/null &&
    compose exec -T api rm -f /tmp/staff.csv /tmp/staff.csv.passwords &&
    compose exec -T api python manage.py loadtest_prepare --password '$pw' \
      --receiver https://hooks.$load.sslip.io --out /tmp/lt.json \
      --experts 400 --ops 40 --history-days 90 --per-day 200 --inspected-per-day 100 \
      --today $today --test-form &&
    compose cp api:/tmp/lt.json /tmp/lt.json && compose exec -T api rm -f /tmp/lt.json"
  # the test data (logins, API key) goes straight to the load server, owner-only
  verify_ip load
  on "deploy@$ip" 'cat /tmp/lt.json && rm -f /tmp/lt.json' \
    | on "root@$load" 'umask 077; mkdir -p /lt; cat > /lt/data.json'
  echo "$host" > "$STATE_DIR/host"; echo "$plan" > "$STATE_DIR/plan"
  say "ready: https://$host (test server), https://hooks.$load.sslip.io (receiver)"
}

# ---------------------------------------------------------------- run

run_one() {   # run_one <dir name> <k> <measured minutes>: one run of the load script
  local name=$1 k=$2 measured=$3 minutes from=25 ip load host
  minutes=$(run_min "$k" "$measured")
  ip=$(ip_of sut); load=$(ip_of load); host=$(cat "$STATE_DIR/host")
  say "${k}x: $((58 * k)) users, ${minutes} min, measured from minute $from"
  on "root@$load" "docker rm -f lt-receiver lt-locust >/dev/null 2>&1 || true
    mkdir -p /lt/out/$name
    docker run -d --name lt-receiver --network lt -v /lt:/lt python:3.12-slim \
      python3 /lt/perf/receiver.py --port 9300 --out /lt/out/$name/webhooks.csv >/dev/null"
  on "deploy@$ip" "nohup bash /tmp/sample.sh /tmp/stats-$name.csv >/dev/null 2>&1 & echo \$! > /tmp/sample.pid"
  on "root@$load" "docker run --rm --name lt-locust --network host -v /lt:/lt -w /lt \
      -e LT_DATA=/lt/data.json -e LT_OUT=/lt/out/$name -e LT_MULT=$k \
      python:3.12-slim sh -c 'pip install -q locust pillow requests >/dev/null 2>&1 &&
        locust -f /lt/perf/loadtest.py --headless --host https://$host \
          -u $((58 * k)) -r 0.3 --run-time ${minutes}m --only-summary > /lt/out/$name/locust.log 2>&1'" \
    || say "the load script ended with an error (results still collected)"
  sleep 60                                         # the last files' checks and PDFs
  on "deploy@$ip" 'kill "$(cat /tmp/sample.pid)" 2>/dev/null; true'
  local out="$RUN_DIR/$name"; mkdir -p "$out"
  on "root@$load" "tar -C /lt/out/$name -czf - ." | tar -C "$out" -xzf -
  on "deploy@$ip" "cat /tmp/stats-$name.csv" > "$out/stats.csv" || true
  # the server's own records, as perf/local/run.sh takes them (SQL through stdin: no size limit)
  local ids bids
  ids=$(cut -d, -f2 "$out/uploads.csv" 2>/dev/null | sed "s/.*/'&'/" | paste -sd, -)
  bids=$(awk -F, '$3=="submitted"{print "'\''"$2"'\''"}' "$out/inspections.csv" 2>/dev/null | paste -sd, -)
  [[ -n "$ids" ]] && echo "select id, extract(epoch from verified_at), status from media_mediaasset where id in ($ids)" \
    | on "deploy@$ip" 'docker exec -i vayu-postgres-1 psql -U vayu -d vayu -At -F,' > "$out/verified.csv"
  [[ -n "$bids" ]] && echo "select id, stage from bookings_booking where id in ($bids)" \
    | on "deploy@$ip" 'docker exec -i vayu-postgres-1 psql -U vayu -d vayu -At -F,' > "$out/stages.csv"
  on "deploy@$ip" 'docker inspect --format "{{.Name}} oom={{.State.OOMKilled}} restarts={{.RestartCount}}" $(docker ps -aq)' > "$out/server-containers.txt" || true
  on "deploy@$ip" 'journalctl -k --no-pager | grep -i "out of memory\|killed process" || true' > "$out/server-oom.txt" || true
  local mem=2048; [[ "$(cat "$STATE_DIR/size")" == base ]] && mem=4096
  python3 "$SRC/perf/report.py" "$out" --from-min "$from" --minutes "$measured" \
    --memory-mb "$mem" > "$out/RESULTS.md" 2>&1 || say "report failed: see $out"
  say "$name: $out/RESULTS.md"
}

cmd_run() {
  local plan size ip load host stamp price hours
  [[ -f "$STATE_DIR/host" ]] || die "up and prepare first"
  plan=$(cat "$STATE_DIR/plan"); [[ "${1:-$plan}" == "$plan" ]] || die "prepared for $plan, not $1"
  size=$(cat "$STATE_DIR/size"); ip=$(ip_of sut); load=$(ip_of load); host=$(cat "$STATE_DIR/host")
  [[ -n "$ip" && -n "$load" ]] || die "up and prepare first"
  read -r _ price _ <<<"$(size_info "$size")"
  hours=2; [[ "$plan" == capacity ]] && hours=6     # capacity: six runs of ~45-70 minutes
  check_budget "$(python3 -c "print($hours * ($price + $LOAD_PRICE))")"
  stamp="$(date -u +%Y%m%d-%H%M)-$size-$plan"; RUN_DIR="$RESULTS/$stamp"; mkdir -p "$RUN_DIR"

  say "the load server: waiting for Docker, then perf/ from $SRC, receiver behind https"
  [[ -f "$SRC/perf/loadtest.py" && -f "$SRC/perf/receiver.py" && -f "$SRC/perf/report.py" ]] \
    || die "no perf/loadtest.py, receiver.py and report.py in $SRC (LT_SRC)"
  until on "root@$load" 'docker info >/dev/null 2>&1'; do sleep 10; done
  tar -C "$SRC" -czf - perf | on "root@$load" 'rm -rf /lt/perf && tar -C /lt -xzf -'
  on "deploy@$ip" 'cat > /tmp/sample.sh' < "$SRC/perf/local/sample.sh"
  on "root@$load" "docker rm -f lt-caddy >/dev/null 2>&1 || true
    docker network create lt >/dev/null 2>&1 || true
    printf 'hooks.$load.sslip.io {\n  reverse_proxy lt-receiver:9300\n}\n' > /lt/Caddyfile
    docker run -d --name lt-caddy --network lt -p 80:80 -p 443:443 -v /lt/Caddyfile:/etc/caddy/Caddyfile caddy:2-alpine >/dev/null"

  if [[ "$plan" == lowcost ]]; then
    run_one lowcost 1 60
  else
    for k in "${CAP_STEPS[@]}"; do
      run_one "step-${k}x" "$k" 15
      if on "deploy@$ip" 'docker inspect --format "{{.State.OOMKilled}} {{.RestartCount}}" $(docker ps -q)' | grep -qv "^false 0$"; then
        say "a service was killed or restarted at ${k}x: the climb stops here"; break
      fi
      if python3 - "$RUN_DIR/step-${k}x/requests.csv" <<'PY'
import csv, sys
rows = [r for r in csv.reader(open(sys.argv[1])) if r] if __import__("os").path.exists(sys.argv[1]) else []
fails = sum(1 for r in rows if r[-1] == "0")           # the load script: 1 = ok, 0 = failed
sys.exit(0 if rows and fails / len(rows) > 0.01 else 1)
PY
      then say "more than 1% of requests failed at ${k}x: the climb stops here"; break; fi
    done
  fi
  echo "{\"size\": \"$size\", \"plan\": \"$plan\", \"host\": \"$host\", \"spent_so_far\": $(spent_now)}" > "$RUN_DIR/run.json"
  say "done: $RUN_DIR"
}

# ---------------------------------------------------------------- clean up and destroy

cmd_down() {
  local ip; ip=$(ip_of sut)
  if [[ -n "$ip" ]]; then
    say "deleting the test bookings' files from the staging bucket (by their IDs only)"
    on "deploy@$ip" 'cd /srv/vayu && source infra/lib.sh && VAYU_TAG=$(cat .deployed) compose exec -T api python manage.py shell -c "
from django.conf import settings
from apps.bookings.models import Booking
from apps.media import storage
from apps.media.models import MediaAsset
from apps.media.services import asset_keys
from apps.reports.models import Report
assert settings.SERVER_KIND == \"test\" and settings.SERVER_NAME.startswith(\"lt-\"), \"not a load-test server\"
ids = list(Booking.objects.filter(booking_id__startswith=\"LT-\").values_list(\"id\", flat=True))
n = 0
for a in MediaAsset.objects.filter(booking_id__in=ids, key__startswith=\"bookings/\"):
    for k in asset_keys(a):
        storage.delete(k); n += 1
for r in Report.objects.filter(booking_id__in=ids).exclude(key=\"\"):
    storage.delete(r.key); n += 1
left = sum(storage.client().list_objects_v2(Bucket=settings.S3_BUCKET, Prefix=f\"bookings/{b}/\").get(\"KeyCount\", 0) for b in ids)
print(f\"deleted {n} files; left under test bookings: {left}\")
"' || say "file clean-up failed: run it again before destroying, or the test files stay in the bucket"
  fi
  local roles=(sut); [[ "${1:-}" == all ]] && roles+=(load)
  for role in "${roles[@]}"; do
    local id; id=$(st field "$role" id)
    [[ -n "$id" ]] || continue
    ours "$id" || die "droplet $id is not one this script made (lt-*, tag $TAG): not touching it"
    say "destroying $role ($id)"
    doctl compute droplet delete "$id" --force
    st drop "$role"
  done
  say "spent so far: \$$(spent_now) (cap \$$CAP)"
}

cmd_status() {
  echo "Ours (tag $TAG):"; doctl compute droplet list --tag-name "$TAG" --format ID,Name,PublicIPv4,Size --no-header || true
  echo "State:"; cat "$STATE"
  echo "Spent so far: \$$(spent_now) of \$$CAP"
}

cmd_lowcost() {
  for size in small mid base; do
    cmd_up "$size"; cmd_prepare lowcost; cmd_run lowcost; cmd_down
  done
  cmd_down all
}

case "${1:-}" in
  up) cmd_up "${2:-}" ;;
  prepare) cmd_prepare "${2:-}" ;;
  run) cmd_run "${2:-}" ;;
  down) cmd_down "${2:-}" ;;
  cost) echo "spent so far: \$$(spent_now) of \$$CAP" ;;
  status) cmd_status ;;
  lowcost) cmd_lowcost ;;
  *) sed -n 2,20p "$0" ;;
esac
