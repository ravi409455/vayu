#!/usr/bin/env bash
# On-demand staging (docs/plan-deploy.md): a powered-off droplet is still billed, so staging is
# kept as a snapshot and only exists while you test. Usually started from GitHub: Actions →
# "staging" → Run workflow → up / down / status (.github/workflows/staging.yml). On the laptop it
# needs doctl signed in, gh signed in, and STAGING_HOST_KEY (below) for "up".
#
#   infra/staging.sh status        is staging up? which snapshots are kept? where does its name point?
#   infra/staging.sh down [--yes]  name → off marker, power off → snapshot → delete (billing stops);
#                                  keeps 2 snapshots ("--yes": no typed confirmation, for GitHub)
#   infra/staging.sh up            create from the newest snapshot (fails if staging is running), with
#                                  staging's fixed SSH key; point its name at it; check the key; start
#                                  the deploy workflow for the newest built commit of main (staging
#                                  deploys, production waits for the owner's Approve, as for a merge)
#
# The name vayu-staging.carcid.in is served by DigitalOcean's DNS (GoDaddy hands just that name
# over with NS records), so this script changes it itself. While staging is off it points to
# 192.0.2.1 (an address reserved for examples: it leads nowhere). The deploy workflow reads that
# marker and skips staging on purpose instead of failing (production then waits too).
#
# Staging's own SSH key is fixed: a server made from a snapshot would get new keys on its first
# boot, so "up" hands the new server the same key (STAGING_HOST_KEY: its private half, from
# GitHub's staging secrets or Phase) and refuses to go on if the server shows any other key.
# GitHub's SSH_KNOWN_HOSTS (the public half) never has to change.
#
# It only ever touches the droplet named "vayu-staging" with the tag "vayu-staging".
set -euo pipefail

NAME=vayu-staging
TAG=vayu-staging
FIREWALL_TAG=vayu-web     # the vayu-web firewall applies to every droplet with this tag
REGION=blr1
SIZE=s-2vcpu-4gb
SSH_KEY_NAME=owner-mac
HOST=vayu-staging.carcid.in
OFF_IP=192.0.2.1          # "staging is off" (keep in step with .github/workflows/deploy.yml)
REPO=ravi409455/vayu
KEEP=2

die() { echo "error: $*" >&2; exit 1; }
command -v doctl >/dev/null || die "install doctl first: brew install doctl"

dns_set() {   # dns_set <ip>: point the staging name at <ip> (TTL 60 s)
  local rid
  rid=$(doctl compute domain records list "$HOST" --format ID,Type,Name --no-header \
    | awk '$2 == "A" && $3 == "@" {print $1}')
  [[ $(grep -c . <<<"$rid") -eq 1 ]] || die "expected one A record for $HOST in DigitalOcean DNS"
  doctl compute domain records update "$HOST" --record-id "$rid" --record-data "$1" --record-ttl 60 >/dev/null
}
dns_now() { dig +short A "$HOST" @ns1.digitalocean.com | tail -1; }
newest_built() {   # the newest commit of main whose images were built by the deploy workflow
  local id sha
  for id in $(gh run list --repo "$REPO" --workflow deploy --branch main --limit 20 \
      --json databaseId -q '.[].databaseId'); do
    sha=$(gh run view "$id" --repo "$REPO" --json headSha,jobs \
      -q 'select(any(.jobs[]; .name == "build" and .conclusion == "success")) | .headSha')
    [[ -n "$sha" ]] && { echo "$sha"; return 0; }
  done
  return 1
}

droplets() { doctl compute droplet list --tag-name "$TAG" --format ID,Name,PublicIPv4 --no-header | awk -v n="$NAME" '$2 == n'; }
snapshots() {   # oldest first: ID NAME
  doctl compute snapshot list --resource droplet --format ID,Name,CreatedAt --no-header \
    | awk -v n="$NAME-" 'index($2, n) == 1' | sort -k3
}

case "${1:-}" in
  status)
    echo "Droplet:"; droplets || true
    echo "Name: $HOST → $(dns_now) $( [[ "$(dns_now)" == "$OFF_IP" ]] && echo "(the off marker)")"
    echo "Snapshots (oldest first):"; snapshots || true
    ;;

  down)
    found=$(droplets)
    [[ -n "$found" ]] || die "staging is not running"
    [[ $(wc -l <<<"$found") -eq 1 ]] || die "more than one $NAME droplet; sort that out in the dashboard"
    id=$(awk '{print $1}' <<<"$found")
    if [[ "${2:-}" != --yes ]]; then
      read -rp "Snapshot and DELETE droplet $NAME ($id)? Type staging to go on: " typed
      [[ "$typed" == staging ]] || die "stopped"
    fi
    snap="$NAME-$(date -u +%Y%m%d-%H%M)"
    # the name leaves the droplet's IP BEFORE the droplet goes: a released IP can go to someone
    # else, and the name must never point at it (wait out the 60 s TTL)
    echo "== pointing $HOST at the off marker $OFF_IP"
    dns_set "$OFF_IP"
    sleep 70
    back_on() {   # a failed down leaves staging as it was: on, with its name
      doctl compute droplet-action power-on "$id" --wait >/dev/null \
        || die "$1; staging could not be powered back on: its name stays on the off marker"
      local now ip
      now=$(droplets); ip=$(awk '{print $3}' <<<"$now")
      # the name only goes back to an address that is still this droplet's (never a released one)
      [[ $(grep -c . <<<"$now") -eq 1 && "$(awk '{print $1}' <<<"$now")" == "$id" && -n "$ip" ]] \
        || die "$1; droplet $id is gone or changed: its name stays on the off marker"
      dns_set "$ip"
      die "$1; staging was NOT deleted: it is back on, with its name"
    }
    echo "== powering off (a clean snapshot)"
    doctl compute droplet-action power-off "$id" --wait >/dev/null || back_on "power-off failed"
    echo "== snapshot $snap (a few minutes)"
    doctl compute droplet-action snapshot "$id" --snapshot-name "$snap" --wait >/dev/null \
      || back_on "the snapshot failed (DigitalOcean token: needs image:create)"
    snapshots | awk '{print $2}' | grep -qx "$snap" || back_on "snapshot $snap not found"
    echo "== deleting the droplet"
    doctl compute droplet delete "$id" --force
    # keep the newest $KEEP snapshots
    all=$(snapshots); n=$(grep -c . <<<"$all" || true); old=""
    (( n > KEEP )) && old=$(head -n $(( n - KEEP )) <<<"$all")   # (macOS head has no -n -2)
    while read -r sid sname _; do
      [[ -n "$sid" ]] || continue
      echo "== deleting old snapshot $sname"; doctl compute snapshot delete "$sid" --force
    done <<<"$old"
    echo "Staging is off. Billing for it stopped (snapshots cost about \$0.06 per GB a month)."
    echo "Its name now points to the off marker: merges skip staging (and production) until 'up'."
    ;;

  up)
    [[ -z "$(droplets)" ]] || die "staging is already running: $(droplets)"
    [[ -n "${STAGING_HOST_KEY:-}" ]] || die "STAGING_HOST_KEY is not set (staging's fixed SSH key; GitHub secret / Phase)"
    command -v gh >/dev/null || die "install gh first: brew install gh"
    snap=$(snapshots | tail -1)
    [[ -n "$snap" ]] || die "no $NAME-* snapshot; build staging from scratch (docs/runbook-new-server.md)"
    key=$(doctl compute ssh-key list --format ID,Name --no-header | awk -v k="$SSH_KEY_NAME" '$2 == k {print $1}')
    [[ -n "$key" ]] || die "no SSH key named $SSH_KEY_NAME in DigitalOcean"
    sha=$(newest_built) || true
    [[ "$sha" =~ ^[0-9a-f]{40}$ ]] || die "could not find the newest built commit of main (gh signed in?)"

    # staging's fixed SSH key goes to the new server through cloud-init (user data), so it never
    # makes keys of its own; only an ED25519 key, the one GitHub's SSH_KNOWN_HOSTS pins.
    # Trade-off (owner's choice, 2026-11-27): DigitalOcean keeps user data in the droplet's
    # metadata (169.254.169.254, readable from inside staging). The app never calls that address
    # (webhooks refuse non-public addresses); staging only, never production.
    tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT; chmod 700 "$tmp"
    printf '%s\n' "$STAGING_HOST_KEY" > "$tmp/key"; chmod 600 "$tmp/key"
    pub=$(ssh-keygen -y -f "$tmp/key") || die "STAGING_HOST_KEY is not a valid private key"
    [[ "$pub" == ssh-ed25519\ * ]] || die "STAGING_HOST_KEY must be an ED25519 key"
    {
      echo "#cloud-config"
      echo "ssh_deletekeys: true"
      echo "ssh_genkeytypes: []"
      echo "ssh_keys:"
      echo "  ed25519_private: |"
      sed 's/^/    /' "$tmp/key"
      echo "  ed25519_public: $pub"
      # once used, no extra copy of this file stays on the disk (the key lives in /etc/ssh)
      echo "runcmd:"
      echo "  - rm -f /var/lib/cloud/instance/user-data.txt /var/lib/cloud/instance/user-data.txt.i"
    } > "$tmp/user-data"

    echo "== creating $NAME from $(awk '{print $2}' <<<"$snap") (a few minutes)"
    doctl compute droplet create "$NAME" --region "$REGION" --size "$SIZE" \
      --image "$(awk '{print $1}' <<<"$snap")" --ssh-keys "$key" --enable-monitoring \
      --tag-names "$TAG,$FIREWALL_TAG" --user-data-file "$tmp/user-data" --wait >/dev/null
    ip=$(droplets | awk '{print $3}')
    echo "== pointing $HOST at $ip"
    dns_set "$ip"
    until [[ "$(dns_now)" == "$ip" ]]; do sleep 5; done
    echo "== waiting for the server to boot"
    until nc -z -w 5 "$ip" 22 2>/dev/null; do sleep 10; done
    shown=""
    for _ in $(seq 1 30); do   # cloud-init puts the key in place within a minute or two of boot
      shown=$(ssh-keyscan -t ed25519 "$ip" 2>/dev/null | awk '!/^#/ {print $2, $3}')
      [[ "$shown" == "$(awk '{print $1, $2}' <<<"$pub")" ]] && break
      sleep 10
    done
    [[ "$shown" == "$(awk '{print $1, $2}' <<<"$pub")" ]] \
      || die "the new server shows an SSH key that is not staging's: NOT deployed (check the droplet; then 'down')"
    echo "== its SSH key is staging's own"

    echo "== starting the deploy workflow for ${sha:0:7} (the newest built commit of main)"
    gh workflow run deploy --repo "$REPO" --ref main -f commit="$sha"
    echo
    echo "Staging is up at https://$HOST. The deploy runs in GitHub (Actions → deploy): staging gets"
    echo "${sha:0:7} in a few minutes; production waits for your Approve, as for a merge."
    echo "When done testing: Actions → staging → down (or infra/staging.sh down)."
    ;;

  *) sed -n '2,24p' "$0"; exit 1 ;;
esac
