#!/usr/bin/env bash
# Load tests on throwaway DigitalOcean servers (docs/plan-load-test.md). Runs on the laptop, with
# doctl signed in and the owner's SSH key. Spend is capped (LT_CAP, default $5).
#
#   perf/cloud.sh up <small|mid|base> [managed]  a test server of that size, the load server (and,
#                                       "managed", a temporary managed Postgres for run D)
#   perf/cloud.sh prepare <lowcost|capacity>  cut it off from staging, deploy main, make the data
#   perf/cloud.sh run <lowcost|capacity> run the load script there, collect the results
#   perf/cloud.sh down [all] [force]    delete the test files, destroy the test server ("all": the
#                                       load server too; "force": destroy even if the clean-up fails)
#   perf/cloud.sh cost | status         spend so far | what is running
#   perf/cloud.sh lowcost               the whole low-cost test: small, mid, base in turn
#   perf/cloud.sh capacity <size>       the whole capacity test on one size
#   perf/cloud.sh dbcheck <size>        run D: the low-cost hour against a temporary managed database
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
# LT_SRC: a checkout to take perf/ from (default: this one). The test server runs main's images,
# so the load-test commands (loadtest_prepare, loadtest_cleanup) must be merged first.
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
DB_SIZE="db-s-1vcpu-1gb"    # run D: the smallest managed Postgres ($15 a month)
DB_PRICE=0.02232

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

db_ours() {   # db_ours <id>: true only for the database this script made (lt-db, tag vayu-loadtest)
  doctl databases get "$1" --format Name,Tags --no-header 2>/dev/null \
    | awk -v t="$TAG" '$1 == "lt-db" && index($2, t) { ok = 1 } END { exit !ok }'
}

make_db() {   # run D: a temporary managed Postgres in Bangalore, reachable only by the test server
  if [[ -n "$(st field db id)" ]]; then say "the managed database is already up"; return; fi
  say "creating the managed database lt-db ($DB_SIZE, a few minutes)"
  local id
  id=$(doctl databases create lt-db --engine pg --version 16 --region "$REGION" --size "$DB_SIZE" \
    --num-nodes 1 --tag "$TAG" --wait --format ID --no-header)
  st set db "{\"id\": \"$id\", \"name\": \"lt-db\", \"ip\": \"\", \"size\": \"$DB_SIZE\", \"price\": $DB_PRICE, \"created\": $(date +%s)}"
}
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

cmd_up() {   # cmd_up <size> [managed]
  [[ "${1:-}" =~ ^(small|mid|base)$ ]] || die "up small, up mid or up base (then 'managed' for run D)"
  [[ -z "${2:-}" || "${2:-}" == managed ]] || die "the second word may only be 'managed'"
  local slug price db=0; read -r slug price _ <<<"$(size_info "$1")"
  [[ "${2:-}" == managed ]] && db=$DB_PRICE
  check_budget "$(python3 -c "print(3 * ($price + $LOAD_PRICE + $db))")"   # a run is ~3 hours
  echo "$1" > "$STATE_DIR/size"
  make_droplet sut "lt-sut-$1" "$slug" "$price"
  local ud="$STATE_DIR/load-user-data.sh"
  printf '#!/bin/sh\ncurl -fsSL https://get.docker.com | sh\n' > "$ud"
  make_droplet load lt-load "$LOAD_SIZE" "$LOAD_PRICE" "$ud"
  [[ "${2:-}" == managed ]] && make_db
  true
}

# ---------------------------------------------------------------- prepare the test server

# How a run is timed (perf/loadtest.py): 58 users per 1× (50 phones, 5 Ops, 3 external-system
# users) sign in at 0.3 a second (the real 20-a-minute limit); the clock starts when all have.
# Minutes 0-55 of the clock are the warm-up: an inspection's files take 25 minutes, then Ops
# review it for 30, so only from minute 55 is every kind of work going on at once. The report
# measures from there: 60 minutes for the low-cost test, 15 for each capacity step.
CAP_STEPS=(1 2 3 4 6 8)
WARM=55
signin_min() { python3 -c "import math; print(math.ceil(58 * $1 / 0.3 / 60))"; }
run_min() { echo $(( $(signin_min "$1") + WARM + $2 + 2 )); }   # run_min <k> <measured minutes>
leads() { python3 -c "import math; print(math.ceil(9 * $1 * ($WARM + $2 + 2) / 60) + 2)"; }

cmd_prepare() {
  local plan=${1:-} size ip host staging sha
  [[ "$plan" == lowcost || "$plan" == capacity ]] || die "prepare lowcost or prepare capacity"
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
  local LT_DB="" dbid; dbid=$(st field db id)
  if [[ -n "$dbid" ]]; then                       # run D: the managed database, test server only
    db_ours "$dbid" || die "database $dbid is not ours: stopped"
    doctl databases firewalls append "$dbid" --rule "droplet:$(st field sut id)" >/dev/null
    LT_DB=$(doctl databases connection "$dbid" --private --format Host,Port,User,Password,Database --no-header)
  fi
  on_staging "deploy@$staging" 'cat /srv/vayu/.env.staging' \
    | LT_DB="$LT_DB" python3 "$ROOT/perf/cloud_env.py" "$host" "lt-$size" "${sizes[@]}" \
    | on "deploy@$ip" 'umask 077; cat > /srv/vayu/.env.staging'
  LT_DB=""
  # the Firebase key: pushes go to Firebase for real, to fake device tokens (owner's choice);
  # only to this throwaway, destroyed after the run
  on_staging "deploy@$staging" 'cat /srv/vayu/secrets/firebase-service-account.json' \
    | on "deploy@$ip" 'umask 077; mkdir -p /srv/vayu/secrets; cat > /srv/vayu/secrets/firebase-service-account.json'
  on "deploy@$ip" 'rm -f /srv/vayu/.phase'   # never fetch staging's settings from Phase here

  say "deploy main ${sha:0:7}"
  on "deploy@$ip" "bash /srv/vayu/infra/deploy.sh $sha"
  on "deploy@$ip" 'cd /srv/vayu && source infra/lib.sh && VAYU_TAG=$(cat .deployed) compose exec -T api python manage.py help loadtest_prepare >/dev/null' \
    || die "this main has no loadtest_prepare yet: merge the load-test code first"

  say "forms and an Admin (setup_platform)"
  local admin_pw; admin_pw=$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')
  on "deploy@$ip" "cd /srv/vayu && source infra/lib.sh && export VAYU_TAG=\$(cat .deployed) &&
    (umask 077; printf 'username,name,role,phone,password\nlt-admin,LT Admin,admin,9700000000,$admin_pw\n' > /tmp/staff.csv) &&
    compose cp /tmp/staff.csv api:/tmp/staff.csv && rm /tmp/staff.csv &&
    compose exec -T api python manage.py setup_platform --users /tmp/staff.csv >/dev/null &&
    compose exec -T api rm -f /tmp/staff.csv /tmp/staff.csv.passwords"
  echo "$host" > "$STATE_DIR/host"
  say "the test form, 3 months of history and the first data (loadtest_prepare)"
  make_data 1 60
  echo "$plan" > "$STATE_DIR/plan"
  say "ready: https://$host (test server), https://hooks.$load.sslip.io (receiver)"
}

# The test data for one run (loadtest_prepare, safe to run again: the history is made once):
# exactly 50k expert and 5k Ops logins, a new password and API key, and fresh leads for today
# (each run's load script starts from the first lead; a lead already inspected cannot start again).
make_data() {   # make_data <k> <measured minutes>
  local k=$1 measured=$2 ip load pw today
  ip=$(ip_of sut); load=$(ip_of load); today=$(leads "$k" "$measured")
  pw=$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')   # this throwaway only
  on "deploy@$ip" "set -o pipefail && cd /srv/vayu && source infra/lib.sh && export VAYU_TAG=\$(cat .deployed) &&
    compose exec -T api python manage.py loadtest_prepare --password '$pw' \
      --receiver https://hooks.$load.sslip.io --out /tmp/lt.json --test-form \
      --experts $((50 * k)) --ops $((5 * k)) --history-days 90 --per-day 200 \
      --inspected-per-day 100 --today $today | tail -1 &&
    compose cp api:/tmp/lt.json /tmp/lt.json && compose exec -T api rm -f /tmp/lt.json"
  # the logins' password and the API key go straight to the load server, owner-only
  verify_ip load
  on "deploy@$ip" 'cat /tmp/lt.json && rm -f /tmp/lt.json' \
    | on "root@$load" 'umask 077; mkdir -p /lt; cat > /lt/data.json'
}

# ---------------------------------------------------------------- run

run_one() {   # run_one <dir name> <k> <measured minutes> [fresh]: one run of the load script
  local name=$1 k=$2 measured=$3 minutes from=$WARM ip load host
  minutes=$(run_min "$k" "$measured")
  ip=$(ip_of sut); load=$(ip_of load); host=$(cat "$STATE_DIR/host")
  [[ "${4:-}" == fresh ]] && make_data "$k" "$measured"
  say "${k}x: $((58 * k)) users, ${minutes} min, measured from minute $from"
  on "root@$load" "docker rm -f lt-receiver lt-locust >/dev/null 2>&1 || true
    mkdir -p /lt/out/$name
    docker run -d --name lt-receiver --network lt -v /lt:/lt python:3.12-slim \
      python3 /lt/perf/receiver.py --port 9300 --out /lt/out/$name/webhooks.csv >/dev/null"
  on "deploy@$ip" "mkdir -p /tmp/lt-$name && nohup bash /tmp/sample.sh /tmp/lt-$name/stats.csv >/dev/null 2>&1 & echo \$! > /tmp/sample.pid"
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
  on "deploy@$ip" "cat /tmp/lt-$name/stats.csv" > "$out/stats.csv" || true
  on "deploy@$ip" "cat /tmp/lt-$name/host.csv" > "$out/host.csv" || true
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
  local mem=2048 cpus=2
  case "$(cat "$STATE_DIR/size")" in small) cpus=1 ;; base) mem=4096 ;; esac
  python3 "$SRC/perf/report.py" "$out" --from-min "$from" --minutes "$measured" \
    --memory-mb "$mem" --cpus "$cpus" > "$out/RESULTS.md" 2>&1 || say "report failed: see $out"
  say "$name: $out/RESULTS.md"
}

stop_reason() {   # stop_reason <step folder> [-v]: false when a real failure ends the climb
  python3 - "$1" "${2:-}" <<'PY'
import json, os, sys
step, verbose = sys.argv[1], sys.argv[2] == "-v"
why = []
try:
    v = json.load(open(os.path.join(step, "verdict.json")))
except (OSError, ValueError):
    why.append("no results for this step")
    v = {"checks": []}
for c in v["checks"]:              # real failures (plan §5); a slow answer alone is only recorded
    if not c["pass"] and c["check"].split(" ")[0] in ("errors", "work", "load"):
        why.append(f"{c['check']}: {c['measured']}")
cont = open(os.path.join(step, "server-containers.txt")).read() \
    if os.path.exists(os.path.join(step, "server-containers.txt")) else ""
if "oom=true" in cont or any(w.startswith("restarts=") and w != "restarts=0" for w in cont.split()):
    why.append("a service was killed for memory or restarted")
if verbose:
    print("; ".join(why) or "no reason")
sys.exit(1 if why else 0)
PY
}

cmd_run() {
  local plan size ip load host stamp price hours
  [[ -f "$STATE_DIR/host" ]] || die "up and prepare first"
  plan=$(cat "$STATE_DIR/plan"); [[ "${1:-$plan}" == "$plan" ]] || die "prepared for $plan, not $1"
  size=$(cat "$STATE_DIR/size"); ip=$(ip_of sut); load=$(ip_of load); host=$(cat "$STATE_DIR/host")
  [[ -n "$ip" && -n "$load" ]] || die "up and prepare first"
  read -r _ price _ <<<"$(size_info "$size")"
  hours=3; [[ "$plan" == capacity ]] && hours=10    # capacity: up to seven runs of ~75-100 min
  check_budget "$(python3 -c "print($hours * ($price + $LOAD_PRICE))")"
  stamp="$(date -u +%Y%m%d-%H%M)-$size-$plan"
  [[ -n "$(st field db id)" ]] && stamp="$stamp-manageddb"
  RUN_DIR="$RESULTS/$stamp"; mkdir -p "$RUN_DIR"

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
    run_one lowcost 1 60       # the data prepare made: 50 experts, 5 Ops, its leads
  else
    local last=""
    for k in "${CAP_STEPS[@]}"; do
      run_one "step-${k}x" "$k" 15 fresh; last=$k
      stop_reason "$RUN_DIR/step-${k}x" && continue
      say "the climb stops at ${k}x: $(stop_reason "$RUN_DIR/step-${k}x" -v)"; break
    done
    python3 "$SRC/perf/summary.py" "$RUN_DIR" > "$RUN_DIR/SUMMARY.md" || true
    # PDFs the first limit: the same load once more with 2 PDFs made at a time (a setting, not a
    # bigger server): does that move the limit?
    local pdf_break
    pdf_break=$(grep -m1 "^- PDF ready p95 <= 30 s: first broke at" "$RUN_DIR/SUMMARY.md" | grep -o "[0-9.]*x$" || true)
    if [[ -n "$pdf_break" && "$(grep -m1 ': first broke at' "$RUN_DIR/SUMMARY.md")" == *"PDF ready"* ]]; then
      local k=${pdf_break%x}
      say "PDFs broke first (at ${k}x): the same step with 2 PDFs at a time"
      on "deploy@$ip" "cd /srv/vayu && sed -i 's/^PDF_CONCURRENCY=.*/PDF_CONCURRENCY=2/' .env.staging &&
        source infra/lib.sh && VAYU_TAG=\$(cat .deployed) compose up -d --no-build pdf-worker >/dev/null"
      run_one "step-${k}x-pdf2" "$k" 15 fresh
      on "deploy@$ip" "cd /srv/vayu && sed -i 's/^PDF_CONCURRENCY=.*/PDF_CONCURRENCY=1/' .env.staging &&
        source infra/lib.sh && VAYU_TAG=\$(cat .deployed) compose up -d --no-build pdf-worker >/dev/null"
      python3 "$SRC/perf/summary.py" "$RUN_DIR" > "$RUN_DIR/SUMMARY.md" || true
    fi
    : "${last:?}"
  fi
  echo "{\"size\": \"$size\", \"plan\": \"$plan\", \"host\": \"$host\", \"spent_so_far\": $(spent_now)}" > "$RUN_DIR/run.json"
  say "done: $RUN_DIR"
}

# ---------------------------------------------------------------- clean up and destroy

cmd_down() {
  local ip; ip=$(ip_of sut)
  if [[ -n "$ip" ]]; then
    say "deleting the test bookings' files from the staging bucket (by their keys only)"
    if ! on "deploy@$ip" 'cd /srv/vayu && source infra/lib.sh && VAYU_TAG=$(cat .deployed) compose exec -T api python manage.py loadtest_cleanup'; then
      # destroying the server now would lose the only list of which files are the test's
      [[ "${1:-}" == force || "${2:-}" == force ]] || die "the clean-up failed: run 'down' again (or 'down force' to destroy anyway and leave the test files in the bucket)"
      say "forced: the test's files stay in the staging bucket"
    fi
  fi
  local dbid; dbid=$(st field db id)
  if [[ -n "$dbid" ]]; then                        # run D's database goes with the test server
    db_ours "$dbid" || die "database $dbid is not one this script made (lt-db, tag $TAG): not touching it"
    say "destroying the managed database ($dbid)"
    doctl databases delete "$dbid" --force
    st drop db
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

cmd_dbcheck() {   # run D: the cheapest passing size, against a temporary managed database
  cmd_up "${1:-}" managed; cmd_prepare lowcost; cmd_run lowcost; cmd_down all
}

cmd_capacity() {
  cmd_up "${1:-}"; cmd_prepare capacity; cmd_run capacity; cmd_down all
}

case "${1:-}" in
  up) cmd_up "${2:-}" "${3:-}" ;;
  prepare) cmd_prepare "${2:-}" ;;
  run) cmd_run "${2:-}" ;;
  down) cmd_down "${2:-}" "${3:-}" ;;
  cost) echo "spent so far: \$$(spent_now) of \$$CAP" ;;
  status) cmd_status ;;
  lowcost) cmd_lowcost ;;
  capacity) cmd_capacity "${2:-}" ;;
  dbcheck) cmd_dbcheck "${2:-}" ;;
  *) sed -n 2,20p "$0" ;;
esac
