#!/usr/bin/env bash
# On-demand staging (docs/plan-deploy.md): a powered-off droplet is still billed, so staging is
# kept as a snapshot and only exists while you test. Run on the laptop, with doctl signed in
# (`doctl auth init`, token from Phase → vayu-owner → DO_API_TOKEN).
#
#   infra/staging.sh status   is staging up? which snapshots are kept?
#   infra/staging.sh down     power off → snapshot → delete the droplet (billing stops); keeps 2 snapshots
#   infra/staging.sh up       create the droplet from the newest snapshot; prints the new IP for DNS
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
KEEP=2

die() { echo "error: $*" >&2; exit 1; }
command -v doctl >/dev/null || die "install doctl first: brew install doctl"

droplets() { doctl compute droplet list --tag-name "$TAG" --format ID,Name,PublicIPv4 --no-header | awk -v n="$NAME" '$2 == n'; }
snapshots() {   # oldest first: ID NAME
  doctl compute snapshot list --resource droplet --format ID,Name,CreatedAt --no-header \
    | awk -v n="$NAME-" 'index($2, n) == 1' | sort -k3
}

case "${1:-}" in
  status)
    echo "Droplet:"; droplets || true
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
    echo "Staging is off. Billing for it stopped (snapshots cost about \$0.06 per GB a month)."
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
    echo
    echo "Staging is up at $ip. Now, at the registrar, change the A record"
    echo "  $HOST → $ip"
    echo "Waiting for DNS to show it (Ctrl-C to stop waiting)..."
    until [[ "$(dig +short "$HOST" @1.1.1.1 | tail -1)" == "$ip" ]]; do sleep 20; done
    echo "DNS is updated. In a minute: https://$HOST/api/v1/health"
    echo "Then deploy what is on main: GitHub → Actions → deploy → Run workflow (latest main commit)."
    ;;

  *) sed -n '2,10p' "$0"; exit 1 ;;
esac
