#!/usr/bin/env bash
# On-demand staging (docs/plan-deploy.md): a powered-off droplet is still billed, so staging is
# kept as a snapshot and only exists while you test. Run on the laptop, with doctl signed in
# (`doctl auth init`, token from Phase → vayu-owner → DO_API_TOKEN).
#
#   infra/staging.sh status   is staging up? which snapshots are kept? where does its name point?
#   infra/staging.sh down     power off → snapshot → delete the droplet (billing stops); keeps 2
#                             snapshots; its name then points to the "off" marker address
#   infra/staging.sh up       create the droplet from the newest snapshot, point its name at it,
#                             deploy the newest built commit of main, check health
#
# The name vayu-staging.carcid.in is served by DigitalOcean's DNS (GoDaddy hands just that name
# over with NS records), so this script changes it itself. While staging is off it points to
# 192.0.2.1 (an address reserved for examples: it leads nowhere). The deploy workflow reads that
# marker and skips staging on purpose instead of failing (production then waits too).
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
    read -rp "Snapshot and DELETE droplet $NAME ($id)? Type staging to go on: " typed
    [[ "$typed" == staging ]] || die "stopped"
    snap="$NAME-$(date -u +%Y%m%d-%H%M)"
    echo "== powering off (a clean snapshot)"
    doctl compute droplet-action power-off "$id" --wait >/dev/null
    echo "== snapshot $snap (a few minutes)"
    doctl compute droplet-action snapshot "$id" --snapshot-name "$snap" --wait >/dev/null
    snapshots | awk '{print $2}' | grep -qx "$snap" || die "snapshot $snap not found; droplet NOT deleted"
    echo "== deleting the droplet"
    doctl compute droplet delete "$id" --force
    # keep the newest $KEEP snapshots
    all=$(snapshots); n=$(grep -c . <<<"$all" || true); old=""
    (( n > KEEP )) && old=$(head -n $(( n - KEEP )) <<<"$all")   # (macOS head has no -n -2)
    while read -r sid sname _; do
      [[ -n "$sid" ]] || continue
      echo "== deleting old snapshot $sname"; doctl compute snapshot delete "$sid" --force
    done <<<"$old"
    dns_set "$OFF_IP"
    echo "Staging is off. Billing for it stopped (snapshots cost about \$0.06 per GB a month)."
    echo "Its name now points to the off marker: merges skip staging (and production) until 'up'."
    ;;

  up)
    [[ -z "$(droplets)" ]] || die "staging is already running: $(droplets)"
    snap=$(snapshots | tail -1)
    [[ -n "$snap" ]] || die "no $NAME-* snapshot; build staging from scratch (docs/runbook-new-server.md)"
    key=$(doctl compute ssh-key list --format ID,Name --no-header | awk -v k="$SSH_KEY_NAME" '$2 == k {print $1}')
    [[ -n "$key" ]] || die "no SSH key named $SSH_KEY_NAME in DigitalOcean"
    echo "== creating $NAME from $(awk '{print $2}' <<<"$snap") (a few minutes)"
    doctl compute droplet create "$NAME" --region "$REGION" --size "$SIZE" \
      --image "$(awk '{print $1}' <<<"$snap")" --ssh-keys "$key" --enable-monitoring \
      --tag-names "$TAG,$FIREWALL_TAG" --wait >/dev/null
    ip=$(droplets | awk '{print $3}')
    echo "== pointing $HOST at $ip"
    dns_set "$ip"
    until [[ "$(dns_now)" == "$ip" ]]; do sleep 5; done
    # the server's own key is in the snapshot: check it under the staging name, whatever the IP
    ssh_s() { ssh -o HostKeyAlias="$HOST" -o ConnectTimeout=10 -o BatchMode=yes "deploy@$ip" "$@"; }
    echo "== waiting for the server to boot"
    until ssh_s true 2>/dev/null; do sleep 10; done
    sha=$(newest_built)
    [[ "$sha" =~ ^[0-9a-f]{40}$ ]] || die "could not find the newest built commit of main (gh signed in?)"
    echo "== deploying ${sha:0:7} (the newest built commit of main)"
    ssh_s "/srv/vayu/infra/deploy.sh $sha"
    echo
    echo "Staging is up at https://$HOST (${sha:0:7}). Its name changed a moment ago: a browser may"
    echo "need a minute. When done testing: infra/staging.sh down"
    ;;

  *) sed -n '2,17p' "$0"; exit 1 ;;
esac
