#!/usr/bin/env bash
# Load tests on throwaway DigitalOcean servers (docs/plan-load-test.md). Runs on the owner's Mac,
# with doctl signed in and the owner's SSH key. Spend over LT_CAP (default $5) gives a loud warning; it never stops a test.
#
#   perf/cloud.sh all            the whole test, in parallel (about 3½ hours):
#                                  low-cost: $12, $18, $24 at the owner's numbers, 60 measured minutes
#                                  capacity: $18 and $24, one continuous run 1× → 8× (15 min a step)
#   perf/cloud.sh dbcheck <size> run D: the low-cost hour on one size against a temporary managed
#                                Postgres (small, mid or base; about 2 hours)
#   perf/cloud.sh status | cost  what is running | spend so far
#   perf/cloud.sh down [force]   clean up and destroy everything this script made ("force": even
#                                if the clean-up of the test's files fails)
#
# Sizes: small = 1 vCPU / 2 GB ($12), mid = 2 vCPU / 2 GB ($18), base = 2 vCPU / 4 GB ($24).
# Load servers: 4 vCPU / 8 GB in Bangalore (uploads from a laptop would test its internet).
# Results: perf/results/<time>-<all|dbcheck>/ (OVERVIEW.md; each test server's folder).
#
# Safety: the account also holds other projects' servers. This script only ever touches droplets
# it made: named lt-* AND tagged vayu-loadtest (and a database lt-db), and only IDs it wrote in its
# state file. Test servers are built fresh (bootstrap.sh + the images of the commit staging runs),
# hold none of staging's data, get an allowlist of staging's settings (server to server, never
# stored on the laptop) with Sentry off, no backups, no heartbeats, never Phase. Files go to the
# staging bucket; every test server deletes its test files (by their keys) before it is destroyed.
# If anything fails, everything is cleaned up and destroyed (LT_KEEP=1 keeps it to look at).
#
# Cloud runs use the test-only form (owner, 2026-11-27): a PDI copy with an extra last page, so an
# inspection sends 100 photos (150 on 2 of every 9) and 15 videos (`loadtest_prepare --test-form`).
# LT_PDF_CONCURRENCY=2 makes 2 PDFs at a time (rerun this way if the capacity test shows that PDFs
# break first: does a setting, not a bigger server, move the limit?).
# LT_SRC: a checkout to take perf/ from (default: this one). The test servers run the commit staging
# runs, so the load-test commands must be merged and deployed to staging first.
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
LOAD_PRICE=0.07143
DB_SIZE="db-s-1vcpu-1gb"    # run D: the smallest managed Postgres ($15 a month)
DB_PRICE=0.02232
STAGING_NAME=vayu-staging
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=30)
mkdir -p "$STATE_DIR" "$RESULTS"
[[ -f "$STATE" ]] || echo '{"spent": 0, "droplets": {}}' > "$STATE"

die() { echo "error: $*" >&2; exit 1; }
say() { echo "== $(date +%H:%M) $*"; }
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

# The test servers of `all`: role → size, plan, load server, receiver port
ROLES=(lc-small lc-mid lc-base cap-mid cap-base)
role_size() { echo "${1#*-}"; }
role_plan() { [[ "$1" == cap-* ]] && echo capacity || echo lowcost; }
role_load() { [[ "$1" == cap-* ]] && echo load-b || echo load-a; }
role_port() {
  case "$1" in lc-small) echo 9301 ;; lc-mid) echo 9302 ;; lc-base) echo 9303 ;;
               cap-mid) echo 9304 ;; cap-base) echo 9305 ;; db-*) echo 9306 ;; esac
}

# How a run is timed (perf/loadtest.py): 58 users per 1× (50 phones, 5 Ops, 3 external-system
# users) sign in at 0.3 a second (the real 20-a-minute limit); the clock starts when all have. An
# inspection's uploads and its Ops review are each paced over 5 minutes (PACE): totals per hour stay
# the owner's, the work is just more bunched (a harsher test, not an easier one), and new work
# settles in 10 minutes (WARM). Low-cost: measured for 60 minutes after the warm-up. Capacity: a
# step lasts while its new users sign in, its new work settles, and 15 minutes are measured.
PACE=5
WARM=$(( 2 * PACE ))
CAP_STEPS="1,2,3,4,6,8"
# real car photos (customer data: kept off git, copied only to the throwaway load servers);
# without the folder, uploads use one made-up photo
PHOTOS="${LT_PHOTOS:-$HOME/vayu-loadtest-photos}"
signin_min() { python3 -c "import math; print(math.ceil(58 * $1 / 0.3 / 60))"; }
capacity_min() {   # the whole capacity run, minutes
  python3 -c "
s = [float(x) for x in '$CAP_STEPS'.split(',')]
m = 58 * s[0] / 0.3 / 60 + $WARM + 15
for a, b in zip(s, s[1:]):
    m += 58 * (b - a) / 0.3 / 60 + $WARM + 15
print(int(m) + 1)"
}
leads() {   # leads <plan>: one inspection every 400 s at 1×, through the run (and a few spare)
  if [[ "$1" == lowcost ]]; then
    python3 -c "import math; print(math.ceil(9 * ($WARM + 60 + 2) / 60) + 3)"
  else
    python3 -c "
import math
s = [float(x) for x in '$CAP_STEPS'.split(',')]
n, prev = 0.0, 0.0
for k in s:
    n += 9 * k * (58 * (k - prev) / 0.3 / 60 + $WARM + 15) / 60
    prev = k
print(math.ceil(n * 1.1) + 5)"
  fi
}

# ---------------------------------------------------------------- state and money

st() {   # st spent | st field <role> <key> | st set <role> <json> | st drop <role> | st roles
  python3 - "$STATE" "$@" <<'PY'
import fcntl, json, sys, time
path, op, args = sys.argv[1], sys.argv[2], sys.argv[3:]
with open(path + ".lock", "w") as lock:              # the test servers finish in parallel
    fcntl.flock(lock, fcntl.LOCK_EX)
    s = json.load(open(path))
    hours = lambda d: -(-(time.time() - d["created"]) // 3600)        # billed in whole hours
    if op == "spent":
        print(round(s["spent"] + sum(hours(d) * d["price"] for d in s["droplets"].values()), 2))
    elif op == "field":
        print(s["droplets"].get(args[0], {}).get(args[1], ""))
    elif op == "roles":
        print(" ".join(s["droplets"]))
    elif op == "set":
        s["droplets"][args[0]] = json.loads(args[1])
    elif op == "drop":                  # destroyed: its cost moves to "spent"
        d = s["droplets"].pop(args[0], None)
        if d:
            s["spent"] += hours(d) * d["price"]
    if op in ("set", "drop"):
        json.dump(s, open(path, "w"), indent=1)
PY
}

spent_now() { st spent; }

check_budget() {   # check_budget <more $ this may cost>: warns loudly, never stops (owner, 2026-11-27)
  python3 -c "import sys; a, b, c = map(float, sys.argv[1:]); sys.exit(0 if a + b <= c else 1)" \
    "$(spent_now)" "$1" "$CAP" && return 0
  printf '\a\n\033[1;41;97m  !!! WARNING: spend could pass $%s (so far $%s, this step up to $%s more). CONTINUING. !!!  \033[0m\n\n' \
    "$CAP" "$(spent_now)" "$1" >&2
}

ours() {   # ours <id>: true only for a droplet this script made (name lt-*, tag vayu-loadtest)
  doctl compute droplet get "$1" --format Name,Tags --no-header 2>/dev/null \
    | awk -v t="$TAG" '$1 ~ /^lt-/ && index($2, t) { ok = 1 } END { exit !ok }'
}

db_ours() {   # db_ours <id>: true only for the database this script made (lt-db, tag vayu-loadtest)
  doctl databases get "$1" --format Name,Tags --no-header 2>/dev/null \
    | awk -v t="$TAG" '$1 == "lt-db" && index($2, t) { ok = 1 } END { exit !ok }'
}

ip_of() { st field "$1" ip; }
pip_of() { st field "$1" pip; }

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

# every compose command on a test server: the production file plus the load-test override
RC='cd /srv/vayu && source infra/lib.sh && export VAYU_TAG=$(cat .deployed) && c() { compose -f perf/cloud-compose.yml "$@"; } &&'

# ---------------------------------------------------------------- create

make_droplet() {   # make_droplet <role> <size slug> <price> [load]
  local role=$1 slug=$2 price=$3 kind=${4:-test} name="lt-$1" out id ip pip key
  if [[ -n "$(ip_of "$role")" ]]; then say "$role already up at $(ip_of "$role")"; return; fi
  key=$(doctl compute ssh-key list --format ID,Name --no-header | awk -v k="$SSH_KEY_NAME" '$2 == k {print $1}')
  [[ -n "$key" ]] || die "no SSH key named $SSH_KEY_NAME in DigitalOcean"
  say "creating $name ($slug)"
  # shellcheck disable=SC2054  # "ID,PublicIPv4,PrivateIPv4" is one doctl value
  local args=(--region "$REGION" --size "$slug" --image ubuntu-24-04-x64 --ssh-keys "$key"
              --enable-monitoring --tag-names "$TAG" --wait
              --format ID,PublicIPv4,PrivateIPv4 --no-header)
  if [[ "$kind" == load ]]; then
    printf '#!/bin/sh\ncurl -fsSL https://get.docker.com | sh\n' > "$STATE_DIR/load-user-data.sh"
    args+=(--user-data-file "$STATE_DIR/load-user-data.sh")
  fi
  out=$(doctl compute droplet create "$name" "${args[@]}")
  id=$(awk '{print $1}' <<<"$out"); ip=$(awk '{print $2}' <<<"$out"); pip=$(awk '{print $3}' <<<"$out")
  st set "$role" "{\"id\": $id, \"name\": \"$name\", \"ip\": \"$ip\", \"pip\": \"$pip\", \"size\": \"$slug\", \"price\": $price, \"created\": $(date +%s)}"
  # a test server gets the web firewall (22, 80, 443) by droplet ID, not by tag (the vayu-web tag
  # carries the Slack alerts). A load server has none: its receivers listen on the private network
  # only, and a firewall would block the test servers' webhooks to them.
  if [[ "$kind" == test ]]; then
    local fw; fw=$(doctl compute firewall list --format ID,Name --no-header | awk '$2 == "vayu-web" {print $1}')
    [[ -n "$fw" ]] && doctl compute firewall add-droplets "$fw" --droplet-ids "$id"
  fi
  ssh-keygen -R "$ip" -f "$STATE_DIR/known_hosts" >/dev/null 2>&1 || true
  until on "root@$ip" -o StrictHostKeyChecking=accept-new true 2>/dev/null; do sleep 5; done
  say "$name is up at $ip"
}

make_db() {   # run D: a temporary managed Postgres in Bangalore, reachable only by its test server
  if [[ -n "$(st field db id)" ]]; then return; fi
  say "creating the managed database lt-db ($DB_SIZE, a few minutes)"
  local id
  id=$(doctl databases create lt-db --engine pg --version 16 --region "$REGION" --size "$DB_SIZE" \
    --num-nodes 1 --tag "$TAG" --wait --format ID --no-header)
  st set db "{\"id\": \"$id\", \"name\": \"lt-db\", \"ip\": \"\", \"size\": \"$DB_SIZE\", \"price\": $DB_PRICE, \"created\": $(date +%s)}"
}

droplet_room() {   # droplet_room <n>: the account may run n more droplets
  local limit used
  limit=$(doctl account get --format DropletLimit --no-header)
  used=$(doctl compute droplet list --format ID --no-header | grep -c . || true)
  (( limit - used >= $1 )) || die "this needs $1 droplets; the account allows $limit and runs $used"
}

# ---------------------------------------------------------------- a test server, start to end

prepare_sut() {   # prepare_sut <role>: bootstrap, settings, deploy, forms, the test form and history
  local role=$1 size ip staging sha load load_ip
  size=$(role_size "$role"); ip=$(ip_of "$role"); load=$(role_load "$role"); load_ip=$(ip_of "$load")
  staging=$(doctl compute droplet list --tag-name "$STAGING_NAME" --format Name,PublicIPv4 --no-header \
    | awk -v n="$STAGING_NAME" '$1 == n {print $2}')
  [[ -n "$staging" ]] || die "staging is not running: its settings are copied from it"
  sha=$(on_staging "deploy@$staging" 'cat /srv/vayu/.deployed')   # built, and known to start
  [[ "$sha" =~ ^[0-9a-f]{40}$ ]] || die "could not read the commit staging runs"

  say "$role: bootstrap (firewall, Docker, deploy user, code); root login is off after it"
  # in the same root session: no nightly backup on a throwaway (it would write into staging's folder)
  { cat "$ROOT/infra/bootstrap.sh"; echo 'systemctl disable --now vayu-backup.timer'; } \
    | on "root@$ip" 'bash -s' >/dev/null

  say "$role: settings (an allowlist of staging's, with the test's changes, server to server)"
  verify_ip "$role"
  local rest sizes; read -r _ _ rest <<<"$(size_info "$size")"; read -ra sizes <<<"$rest"
  # LT_PDF_CONCURRENCY=2: PDFs made 2 at a time (rerun when the capacity test shows PDFs break first)
  [[ -n "${LT_PDF_CONCURRENCY:-}" ]] && sizes+=("PDF_CONCURRENCY=$LT_PDF_CONCURRENCY")
  local LT_DB="" dbid; dbid=$(st field db id)
  if [[ "$role" == db-* && -n "$dbid" ]]; then    # run D: the managed database, this server only
    db_ours "$dbid" || die "database $dbid is not ours: stopped"
    doctl databases firewalls append "$dbid" --rule "droplet:$(st field "$role" id)" >/dev/null
    LT_DB=$(doctl databases connection "$dbid" --private --format Host,Port,User,Password,Database --no-header)
  fi
  on_staging "deploy@$staging" 'cat /srv/vayu/.env.staging' \
    | LT_DB="$LT_DB" python3 "$ROOT/perf/cloud_env.py" "$ip" "lt-$role" "${sizes[@]}" \
    | on "deploy@$ip" 'umask 077; cat > /srv/vayu/.env.staging'
  LT_DB=""
  # the Firebase key: pushes go to Firebase for real, to fake device tokens (owner's choice)
  on_staging "deploy@$staging" 'cat /srv/vayu/secrets/firebase-service-account.json' \
    | on "deploy@$ip" 'umask 077; mkdir -p /srv/vayu/secrets; cat > /srv/vayu/secrets/firebase-service-account.json'
  on "deploy@$ip" 'rm -f /srv/vayu/.phase'      # never fetch staging's settings from Phase here

  say "$role: deploy ${sha:0:7} (staging's commit) with the load-test settings"
  on "deploy@$ip" "cd /srv/vayu && git fetch -q origin && git checkout -q --detach $sha && echo $sha > .deployed"
  # the load-test settings come from this checkout (fixes here need no staging deploy)
  tar -C "$SRC" -cf - perf/cloud-compose.yml perf/cloud.Caddyfile perf/local/loadtest_settings.py \
    | on "deploy@$ip" 'tar -C /srv/vayu -xf -'
  on "deploy@$ip" "$RC c pull -q && c up -d --no-build --remove-orphans" >/dev/null
  local t=0
  until curl -fsk --max-time 5 "https://$ip/api/v1/health" 2>/dev/null | grep -q '"ok"'; do
    (( t += 10 )); (( t < 600 )) || die "$role is not healthy after 10 minutes"
    sleep 10
  done
  on "deploy@$ip" "$RC c exec -T api python manage.py help loadtest_prepare >/dev/null" \
    || die "commit ${sha:0:7} has no loadtest_prepare: merge the load-test code and let staging deploy it"

  say "$role: forms and an Admin (setup_platform), the test form and 3 months of history"
  local admin_pw; admin_pw=$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')
  on "deploy@$ip" "$RC
    printf 'username,name,role,phone,password\nlt-admin,LT Admin,admin,9700000000,$admin_pw\n' |
      c exec -T api sh -c 'umask 077 && cat > /tmp/staff.csv' &&
    c exec -T api python manage.py setup_platform --users /tmp/staff.csv >/dev/null &&
    c exec -T api rm -f /tmp/staff.csv /tmp/staff.csv.passwords"
  local k_max=1; [[ "$(role_plan "$role")" == capacity ]] && k_max=${CAP_STEPS##*,}
  local pw; pw=$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')   # this throwaway only
  # webhooks go to this server's receiver on its load server over the private network (plain
  # http, allowed by the load-test settings only); leads unassigned: the load script's Ops give
  # each to a free phone, so it works however many phones a step has
  on "deploy@$ip" "set -o pipefail && $RC
    c exec -T api python manage.py loadtest_prepare --password '$pw' \
      --receiver http://$(pip_of "$load"):$(role_port "$role") --out /tmp/lt.json --test-form \
      --experts $((50 * k_max)) --ops $((5 * k_max)) --history-days 90 --per-day 200 \
      --inspected-per-day 100 --today $(leads "$(role_plan "$role")") --unassigned | tail -1 &&
    c cp api:/tmp/lt.json /tmp/lt.json && c exec -T api rm -f /tmp/lt.json"
  # the logins' password and the API key go straight to the load server, owner-only
  verify_ip "$load"
  on "deploy@$ip" 'cat /tmp/lt.json && rm -f /tmp/lt.json' \
    | on "root@$load_ip" "umask 077; mkdir -p /lt; cat > /lt/data-$role.json"
  on "deploy@$ip" 'cat > /tmp/sample.sh' < "$SRC/perf/local/sample.sh"
}

run_sut() {   # run_sut <role> <results folder>: one run of the load script, then the results
  local role=$1 out=$2 plan ip load_ip size port
  plan=$(role_plan "$role"); ip=$(ip_of "$role"); size=$(role_size "$role")
  load_ip=$(ip_of "$(role_load "$role")"); port=$(role_port "$role")
  local minutes env_plan
  if [[ "$plan" == lowcost ]]; then
    minutes=$(( $(signin_min 1) + WARM + 60 + 2 ))
    env_plan="-e LT_MULT=1"
  else
    minutes=$(( $(capacity_min) + 10 ))       # the plan stops it; this is only a safety limit
    env_plan="-e LT_STEPS=$CAP_STEPS -e LT_STEP_MINUTES=15"
  fi
  local env_photos=""
  [[ -d "$PHOTOS" ]] && env_photos="-e LT_PHOTOS=/lt/photos"
  say "$role: $plan run, up to $minutes minutes"
  on "root@$load_ip" "docker rm -f lt-recv-$role lt-locust-$role >/dev/null 2>&1 || true
    mkdir -p /lt/out/$role
    docker run -d --name lt-recv-$role -p $(pip_of "$(role_load "$role")"):$port:9300 -v /lt:/lt \
      python:3.12-slim python3 /lt/perf/receiver.py --port 9300 --out /lt/out/$role/webhooks.csv >/dev/null"
  on "deploy@$ip" "mkdir -p /tmp/lt && nohup bash /tmp/sample.sh /tmp/lt/stats.csv >/dev/null 2>&1 & echo \$! > /tmp/sample.pid"
  # detached on the load server: a dropped connection or a sleeping laptop does not stop the run;
  # this side waits for it, reconnecting as often as it needs to
  on "root@$load_ip" "docker run -d --name lt-locust-$role --network host -v /lt:/lt -w /lt \
      -e LT_DATA=/lt/data-$role.json -e LT_OUT=/lt/out/$role -e LT_TLS_VERIFY=0 \
      -e LT_UPLOAD_MINUTES=$PACE -e LT_REVIEW_MINUTES=$PACE $env_plan $env_photos \
      python:3.12-slim sh -c 'pip install -q locust pillow requests >/dev/null 2>&1 &&
        locust -f /lt/perf/loadtest.py --headless --host https://$ip \
          -u 58 -r 0.3 --run-time ${minutes}m --only-summary > /lt/out/$role/locust.log 2>&1'" >/dev/null
  until on "root@$load_ip" "docker wait lt-locust-$role >/dev/null 2>&1; ! docker ps -q --filter name=lt-locust-$role | grep -q ." 2>/dev/null; do
    sleep 30
  done
  sleep 60                                         # the last files' checks and PDFs
  on "deploy@$ip" 'kill "$(cat /tmp/sample.pid)" 2>/dev/null; true'
  mkdir -p "$out"
  on "root@$load_ip" "tar -C /lt/out/$role -czf - ." | tar -C "$out" -xzf -
  on "deploy@$ip" 'cat /tmp/lt/stats.csv' > "$out/stats.csv" || true
  on "deploy@$ip" 'cat /tmp/lt/host.csv' > "$out/host.csv" || true
  # the server's own records, through the app (works with a managed database too)
  cut -d, -f2 "$out/uploads.csv" 2>/dev/null \
    | on "deploy@$ip" "$RC c exec -T api python manage.py loadtest_records files" > "$out/verified.csv" || true
  awk -F, '$3=="submitted"{print $2}' "$out/inspections.csv" 2>/dev/null \
    | on "deploy@$ip" "$RC c exec -T api python manage.py loadtest_records stages" > "$out/stages.csv" || true
  on "deploy@$ip" 'docker inspect --format "{{.Name}} oom={{.State.OOMKilled}} restarts={{.RestartCount}}" $(docker ps -aq)' > "$out/server-containers.txt" || true
  on "deploy@$ip" 'journalctl -k --no-pager | grep -i "out of memory\|killed process" || true' > "$out/server-oom.txt" || true
  local mem=2048 cpus=2
  case "$size" in small) cpus=1 ;; base) mem=4096 ;; esac
  if [[ "$plan" == lowcost ]]; then
    python3 "$SRC/perf/report.py" "$out" --from-min "$WARM" --minutes 60 --memory-mb "$mem" \
      --cpus "$cpus" > "$out/RESULTS.md" 2>&1 || say "$role: report failed"
  else
    awk -F, '$2=="step"{print $3}' "$out/run.csv" | while read -r k; do
      python3 "$SRC/perf/report.py" "$out" --step "$k" --memory-mb "$mem" --cpus "$cpus" \
        > "$out/RESULTS-${k}x.md" 2>&1 || say "$role: report for ${k}x failed"
    done
    python3 "$SRC/perf/summary.py" "$out" > "$out/SUMMARY.md" 2>&1 || true
  fi
  say "$role: results in $out"
}

cleanup_destroy() {   # cleanup_destroy <role> [force]: the test's files out of the bucket, then destroy
  local role=$1 id ip
  id=$(st field "$role" id); ip=$(ip_of "$role")
  [[ -n "$id" ]] || return 0
  if [[ "$role" != load-* ]]; then
    if ! on "deploy@$ip" "$RC c exec -T api python manage.py loadtest_cleanup" >/dev/null 2>&1; then
      # destroying the server now would lose the only list of which files are the test's
      [[ "${2:-}" == force ]] || die "$role: the clean-up failed: run 'down' again (or 'down force')"
      say "$role: forced: its test files stay in the staging bucket"
    fi
  fi
  ours "$id" || die "droplet $id is not one this script made (lt-*, tag $TAG): not touching it"
  doctl compute droplet delete "$id" --force
  st drop "$role"
  say "$role destroyed"
}

sut_job() {   # sut_job <role> <results>: one test server from start to end (in the background)
  local role=$1 dir=$2
  trap 'rc=$?; (( rc == 0 )) || [[ -n "${LT_KEEP:-}" ]] || cleanup_destroy "$role" force' EXIT
  prepare_sut "$role"
  run_sut "$role" "$dir/$role"
  cleanup_destroy "$role"
}

# ---------------------------------------------------------------- the commands

cmd_down() {   # everything this script made: test servers first (their files), then the rest
  local role dbid
  for role in $(st roles); do
    [[ "$role" == load-* || "$role" == db ]] && continue
    cleanup_destroy "$role" "${1:-}"
  done
  for role in $(st roles); do [[ "$role" == load-* ]] && cleanup_destroy "$role"; done
  dbid=$(st field db id)
  if [[ -n "$dbid" ]]; then
    db_ours "$dbid" || die "database $dbid is not one this script made (lt-db, tag $TAG): not touching it"
    doctl databases delete "$dbid" --force
    st drop db
    say "the managed database destroyed"
  fi
  say "spent so far: \$$(spent_now) (warning above \$$CAP)"
}

on_failure_destroy() {   # a whole-test command that fails cleans up and destroys everything
  # shellcheck disable=SC2154  # rc is set inside the trap
  trap 'rc=$?; if (( rc != 0 )) && [[ -z "${LT_KEEP:-}" ]]; then
          echo "== failed (exit $rc): cleaning up and destroying, so nothing keeps billing" >&2
          cmd_down force || echo "== DESTROY FAILED: run perf/cloud.sh status, then down force" >&2
        fi' EXIT INT TERM
}

load_ready() {   # load_ready <load role>: Docker installed (cloud-init), perf/ copied
  local ip; ip=$(ip_of "$1")
  until on "root@$ip" 'docker info >/dev/null 2>&1'; do sleep 10; done
  tar -C "$SRC" -czf - perf | on "root@$ip" 'rm -rf /lt/perf && mkdir -p /lt && tar -C /lt -xzf -'
  if [[ -d "$PHOTOS" ]]; then
    tar -C "$PHOTOS" -cf - . | on "root@$ip" 'rm -rf /lt/photos && mkdir -m 700 /lt/photos && tar -C /lt/photos -xf -'
  fi
}

overview() {   # overview <results folder>: one page over every test server
  python3 - "$1" <<'PY'
import glob, json, os, sys
run = sys.argv[1]
out = ["# Load test: overview\n"]
for d in sorted(glob.glob(os.path.join(run, "*/"))):
    role = os.path.basename(d.rstrip("/"))
    v = os.path.join(d, "verdict.json")
    if os.path.exists(v):
        j = json.load(open(v))
        f = j.get("facts", {})
        out.append(f"- **{role}**: {'every check passed' if j['pass'] else 'NOT every check passed'}"
                   f" (API p95 {f.get('api_p95_ms', float('nan')):.0f} ms, PDF p95 "
                   f"{f.get('pdf_p95_s', float('nan')):.1f} s, memory {f.get('memory_peak_mib', 0):.0f}"
                   f" MiB, CPU p95 {f.get('cpu_p95_pct', float('nan')):.0f}%): {role}/RESULTS.md")
    elif os.path.exists(os.path.join(d, "SUMMARY.md")):
        top = [x for x in open(os.path.join(d, "SUMMARY.md")) if x.startswith("- Every check")]
        out.append(f"- **{role}**: {top[0][2:].strip() if top else 'see SUMMARY.md'}: {role}/SUMMARY.md")
    else:
        out.append(f"- **{role}**: no results (see its log)")
print("\n".join(out))
PY
}

cmd_all() {
  on_failure_destroy
  [[ -f "$SRC/perf/loadtest.py" && -f "$SRC/perf/receiver.py" && -f "$SRC/perf/report.py" ]] \
    || die "no perf/loadtest.py, receiver.py and report.py in $SRC (LT_SRC)"
  local hours price total=0
  for role in "${ROLES[@]}"; do
    read -r _ price _ <<<"$(size_info "$(role_size "$role")")"
    hours=3; [[ "$role" == cap-* ]] && hours=5
    total=$(python3 -c "print($total + $hours * $price)")
  done
  check_budget "$(python3 -c "print($total + 3 * $LOAD_PRICE + 5 * $LOAD_PRICE)")"
  droplet_room 7
  local dir; dir="$RESULTS/$(date -u +%Y%m%d-%H%M)-all"; mkdir -p "$dir"
  say "creating 5 test servers and 2 load servers (results: $dir)"
  for role in "${ROLES[@]}"; do
    local slug; read -r slug price _ <<<"$(size_info "$(role_size "$role")")"
    make_droplet "$role" "$slug" "$price"
  done
  make_droplet load-a "$LOAD_SIZE" "$LOAD_PRICE" load
  make_droplet load-b "$LOAD_SIZE" "$LOAD_PRICE" load
  load_ready load-a; load_ready load-b
  local pids=() lc=() cap=()
  for role in "${ROLES[@]}"; do
    sut_job "$role" "$dir" > "$dir/$role.log" 2>&1 &
    pids+=($!)
    if [[ "$role" == cap-* ]]; then cap+=($!); else lc+=($!); fi
    say "$role started (log: $dir/$role.log)"
  done
  local failed=0 p
  for p in "${lc[@]}"; do wait "$p" || failed=1; done
  cleanup_destroy load-a                      # low-cost is done: its load server stops billing
  say "low-cost done: $(overview "$dir" | grep -c 'every check') results so far"
  for p in "${cap[@]}"; do wait "$p" || failed=1; done
  cleanup_destroy load-b
  overview "$dir" > "$dir/OVERVIEW.md"
  cat "$dir/OVERVIEW.md"
  say "spent: \$$(spent_now) (warning above \$$CAP)"
  (( failed == 0 )) || die "a test server failed: see its log in $dir"
}

cmd_dbcheck() {   # run D: one size, its data on a temporary managed database
  [[ "${1:-}" =~ ^(small|mid|base)$ ]] || die "dbcheck small, dbcheck mid or dbcheck base"
  on_failure_destroy
  local role="db-$1" slug price
  read -r slug price _ <<<"$(size_info "$1")"
  check_budget "$(python3 -c "print(3 * ($price + $LOAD_PRICE + $DB_PRICE))")"
  droplet_room 2
  local dir; dir="$RESULTS/$(date -u +%Y%m%d-%H%M)-dbcheck"; mkdir -p "$dir"
  make_droplet "$role" "$slug" "$price"
  make_droplet load-a "$LOAD_SIZE" "$LOAD_PRICE" load
  make_db
  load_ready load-a
  sut_job "$role" "$dir" 2>&1 | tee "$dir/$role.log"
  cleanup_destroy load-a
  cmd_down
  overview "$dir" > "$dir/OVERVIEW.md"; cat "$dir/OVERVIEW.md"
}

cmd_status() {
  echo "Ours (tag $TAG):"; doctl compute droplet list --tag-name "$TAG" --format ID,Name,PublicIPv4,Size --no-header || true
  echo "State:"; cat "$STATE"
  echo "Spent so far: \$$(spent_now) (warning above \$$CAP)"
}

# the long commands keep the Mac awake (caffeinate) for as long as they run
if [[ "${1:-}" =~ ^(all|dbcheck)$ && -z "${LT_AWAKE:-}" ]] && command -v caffeinate >/dev/null; then
  LT_AWAKE=1 exec caffeinate -i "$0" "$@"
fi

case "${1:-}" in
  all) cmd_all ;;
  dbcheck) cmd_dbcheck "${2:-}" ;;
  down) cmd_down "${2:-}" ;;
  cost) echo "spent so far: \$$(spent_now) (warning above \$$CAP)" ;;
  status) cmd_status ;;
  *) sed -n 2,16p "$0" ;;
esac
