#!/usr/bin/env bash
# Load tests on throwaway DigitalOcean servers (docs/plan-load-test.md). Runs on the laptop, with
# doctl signed in and the owner's SSH key. Spend is capped (LT_CAP, default $5).
#
#   perf/cloud.sh up <small|mid|base>   create a test server of that size (and the load server)
#   perf/cloud.sh prepare               cut it off from staging, deploy main, make the test data
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
on() { local who=$1; shift; ssh "${SSH_OPTS[@]}" "$who" "$@"; }

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
  ssh-keygen -R "$ip" >/dev/null 2>&1 || true
  until ssh "${SSH_OPTS[@]}" -o StrictHostKeyChecking=accept-new "root@$ip" true 2>/dev/null; do sleep 5; done
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

cmd_prepare() {
  local size ip host staging sha
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

  say "settings: staging's, changed for the test (copied server to server)"
  local rest sizes; read -r _ _ rest <<<"$(size_info "$size")"; read -ra sizes <<<"$rest"
  ssh "${SSH_OPTS[@]}" "deploy@$staging" 'cat /srv/vayu/.env.staging' \
    | python3 "$ROOT/perf/cloud_env.py" "$host" "lt-$size" "${sizes[@]}" \
    | ssh "${SSH_OPTS[@]}" "deploy@$ip" 'umask 077; cat > /srv/vayu/.env.staging'
  ssh "${SSH_OPTS[@]}" "deploy@$staging" 'cat /srv/vayu/secrets/firebase-service-account.json' \
    | ssh "${SSH_OPTS[@]}" "deploy@$ip" 'umask 077; mkdir -p /srv/vayu/secrets; cat > /srv/vayu/secrets/firebase-service-account.json'
  on "deploy@$ip" 'rm -f /srv/vayu/.phase'   # never fetch staging's settings from Phase here

  say "deploy main ${sha:0:7}"
  on "deploy@$ip" "bash /srv/vayu/infra/deploy.sh $sha"
  on "deploy@$ip" 'cd /srv/vayu && source infra/lib.sh && VAYU_TAG=$(cat .deployed) compose exec -T api python manage.py help loadtest_prepare >/dev/null' \
    || die "this main has no loadtest_prepare yet: merge the load-test code first"

  say "forms and an Admin (setup_platform), then the test data (loadtest_prepare)"
  # random, used only on this throwaway (destroyed after the run)
  local pw admin_pw
  pw=$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')
  admin_pw=$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')
  local load; load=$(ip_of load)
  on "deploy@$ip" "cd /srv/vayu && source infra/lib.sh && export VAYU_TAG=\$(cat .deployed) &&
    printf 'username,name,role,phone,password\nlt-admin,LT Admin,admin,9700000000,$admin_pw\n' > /tmp/staff.csv &&
    compose cp /tmp/staff.csv api:/tmp/staff.csv && rm /tmp/staff.csv &&
    compose exec -T api python manage.py setup_platform --users /tmp/staff.csv >/dev/null &&
    compose exec -T api python manage.py loadtest_prepare --password '$pw' \
      --receiver https://hooks.$load.sslip.io --out /tmp/lt.json --experts 400 --ops 40 \
      --test-form &&
    compose cp api:/tmp/lt.json /tmp/lt.json"
  # the test data goes to the load server (it holds logins and the API key: owner-only files)
  on "deploy@$ip" 'cat /tmp/lt.json && rm -f /tmp/lt.json' \
    | on "root@$load" 'umask 077; mkdir -p /lt; cat > /lt/data.json'
  echo "$host" > "$STATE_DIR/host"
  say "ready: https://$host (test server), https://hooks.$load.sslip.io (receiver)"
}

# ---------------------------------------------------------------- run

cmd_run() {
  local plan=$1 size ip load host out stamp
  [[ "$plan" == lowcost || "$plan" == capacity ]] || die "run lowcost or run capacity"
  [[ -f "$STATE_DIR/host" ]] || die "up and prepare first"
  size=$(cat "$STATE_DIR/size"); ip=$(ip_of sut); load=$(ip_of load); host=$(cat "$STATE_DIR/host")
  [[ -n "$ip" && -n "$load" ]] || die "up and prepare first"
  read -r _ price _ <<<"$(size_info "$size")"
  local hours=2; [[ "$plan" == capacity ]] && hours=3
  check_budget "$(python3 -c "print($hours * ($price + $LOAD_PRICE))")"
  stamp="$(date -u +%Y%m%d-%H%M)-$size-$plan"; out="$RESULTS/$stamp"; mkdir -p "$out"

  say "the load server: waiting for Docker, then perf/ from $SRC, receiver behind https"
  until on "root@$load" 'docker info >/dev/null 2>&1'; do sleep 10; done
  [[ -f "$SRC/perf/loadtest.py" && -f "$SRC/perf/receiver.py" ]] || die "no perf/loadtest.py and perf/receiver.py in $SRC (LT_SRC)"
  tar -C "$SRC" -czf - perf | on "root@$load" 'rm -rf /lt/perf && tar -C /lt -xzf -'
  on "root@$load" "docker rm -f lt-receiver lt-caddy lt-locust >/dev/null 2>&1 || true
    mkdir -p /lt/out && docker network create lt >/dev/null 2>&1 || true
    docker run -d --name lt-receiver --network lt -v /lt:/lt python:3.12-slim \
      python3 /lt/perf/receiver.py --port 9300 --out /lt/out/webhooks.csv >/dev/null
    printf 'hooks.$load.sslip.io {\n  reverse_proxy lt-receiver:9300\n}\n' > /lt/Caddyfile
    docker run -d --name lt-caddy --network lt -p 80:80 -p 443:443 -v /lt/Caddyfile:/etc/caddy/Caddyfile caddy:2-alpine >/dev/null"

  say "server sampler (memory, load, containers, every 5 s)"
  on "deploy@$ip" 'nohup sh -c "while :; do date -u +%FT%TZ; free -m | sed -n 2,3p; cat /proc/loadavg; docker stats --no-stream --format \"{{.Name}} {{.CPUPerc}} {{.MemUsage}}\"; echo; sleep 5; done" > /tmp/lt-metrics.log 2>&1 & echo $! > /tmp/lt-metrics.pid'

  local steps=(1); local minutes=90
  [[ "$plan" == capacity ]] && { steps=(1 2 3 4 6 8); minutes=15; }
  for k in "${steps[@]}"; do
    say "step ${k}x for ${minutes} min (results: $out)"
    on "root@$load" "docker run --rm --name lt-locust --network host -v /lt:/lt -w /lt \
      -e LT_DATA=/lt/data.json -e LT_OUT=/lt/out/step-$k -e LT_MULT=$k \
      python:3.12-slim sh -c 'pip install -q locust pillow requests >/dev/null 2>&1 &&
        mkdir -p /lt/out/step-$k && locust -f /lt/perf/loadtest.py --headless \
        --host https://$host --run-time ${minutes}m --csv /lt/out/step-$k/locust \
        -u \$((58 * $k)) -r 2'" || say "step ${k}x ended with an error (kept going to collect)"
    if [[ "$plan" == capacity ]] && on "deploy@$ip" 'docker ps -a --format "{{.Names}} {{.Status}}" | grep -qi "oom\|restarting"'; then
      say "a service was killed or is restarting: stopping the climb at ${k}x"; break
    fi
  done

  say "collecting"
  on "deploy@$ip" 'kill "$(cat /tmp/lt-metrics.pid)" 2>/dev/null; cat /tmp/lt-metrics.log' > "$out/server-metrics.log" || true
  on "deploy@$ip" 'docker ps -a --format "{{.Names}} {{.Status}}"; docker inspect --format "{{.Name}} oom={{.State.OOMKilled}} restarts={{.RestartCount}}" $(docker ps -aq)' > "$out/server-containers.txt" || true
  on "deploy@$ip" 'journalctl -k --no-pager | grep -i "out of memory\|killed process" || true' > "$out/server-oom.txt" || true
  on "root@$load" 'tar -C /lt -czf - out' | tar -C "$out" -xzf -
  if [[ -f "$SRC/perf/report.py" ]]; then
    python3 "$SRC/perf/report.py" "$out/out" > "$out/report.md" 2>&1 || say "report failed: see $out"
  fi
  echo "{\"size\": \"$size\", \"plan\": \"$plan\", \"host\": \"$host\", \"spent_so_far\": $(spent_now)}" > "$out/run.json"
  say "done: $out"
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
    cmd_up "$size"; cmd_prepare; cmd_run lowcost; cmd_down
  done
  cmd_down all
}

case "${1:-}" in
  up) cmd_up "${2:-}" ;;
  prepare) cmd_prepare ;;
  run) cmd_run "${2:-}" ;;
  down) cmd_down "${2:-}" ;;
  cost) echo "spent so far: \$$(spent_now) of \$$CAP" ;;
  status) cmd_status ;;
  lowcost) cmd_lowcost ;;
  *) sed -n 2,20p "$0" ;;
esac
