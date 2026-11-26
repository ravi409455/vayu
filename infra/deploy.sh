#!/usr/bin/env bash
# Deploy one commit of main on this server: infra/deploy.sh <full commit id>
#
# GitHub Actions' key may run ONLY this script (authorized_keys: command="...deploy.sh",restrict),
# and passes the commit id as SSH_ORIGINAL_COMMAND. The worst a leaked key can do is deploy a
# commit that is already on main and already built.
#
# Steps: check the commit is on main → (production) dump the database → check out that commit's
# infra files → pull its images → migrate and restart → wait for /api/v1/health to say ok.
# If health fails, the previous commit's images go back (safe: every migration must also work
# with the previous release, docs/plan-deploy.md §1a). The database is never rolled back here.

# git checkout below rewrites this file while bash is still reading it: run from a copy.
if [[ -z "${VAYU_DEPLOY_COPY:-}" ]]; then
  copy=$(mktemp)
  cp "$0" "$copy"
  VAYU_DEPLOY_COPY=1 VAYU_INFRA="$(cd "$(dirname "$0")" && pwd)" exec bash "$copy" "$@"
fi
# shellcheck source=infra/lib.sh
source "$VAYU_INFRA/lib.sh"

# "<commit>" or "<commit> rollback" (a rollback started by hand may go back to an older commit)
read -r SHA MODE EXTRA <<<"${SSH_ORIGINAL_COMMAND:-$*}"
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || die "give the full 40-character commit id"
[[ -z "${MODE:-}" || "$MODE" == rollback ]] && [[ -z "${EXTRA:-}" ]] || die "usage: deploy.sh <commit> [rollback]"

git fetch --quiet origin main
git merge-base --is-ancestor "$SHA" origin/main || die "$SHA is not on main"

PREV=$(cat .deployed 2>/dev/null || true)

# Never backwards by accident: two merges close together can finish their builds out of order, and
# the older one must not replace the newer one. Only a rollback started by hand goes back.
if [[ -n "$PREV" && "${MODE:-}" != rollback ]] && ! git merge-base --is-ancestor "$PREV" "$SHA"; then
  echo "== $SHA is not newer than the live ${PREV:0:7}: nothing to do (a rollback is started by hand)"
  exit 0
fi

# the server's settings, fresh from Phase (a secret changed there arrives with this deploy)
bash "$VAYU_INFRA/secrets.sh"
[[ -f "$VAYU_ENV_FILE" ]] || die "no $VAYU_ENV_FILE (and no .phase to fetch it from Phase)"
APP_HOST=$(envval APP_HOST)

# Private images (once the repo is private): a read-only package token in the env file.
if [[ -n "$(envval GHCR_TOKEN)" ]]; then
  envval GHCR_TOKEN | docker login ghcr.io -u "$(envval GHCR_USER)" --password-stdin >/dev/null
fi

if [[ "$(envval VAYU_SERVER_KIND)" == "production" && -n "$PREV" ]]; then
  echo "== safety copy of the database before the release"
  bash "$VAYU_DIR/infra/backup.sh" "predeploy-${SHA:0:7}"
fi

up() {   # up <commit>: that commit's compose file, scripts and images
  # (set -e is off inside a function called from an if, so each step says when it failed)
  git checkout --quiet --detach "$1" || return 1
  export VAYU_TAG=$1
  compose pull --quiet || return 1
  compose up -d --no-build --remove-orphans || return 1
}

healthy() {   # up to 3 minutes for {"status": "ok"} (database, Redis, storage, workers, push)
  for _ in $(seq 36); do
    if curl -fsS --max-time 5 --resolve "$APP_HOST:443:127.0.0.1" "https://$APP_HOST/api/v1/health" \
        2>/dev/null | grep -q '"ok"'; then return 0; fi
    sleep 5
  done
  return 1
}

echo "== deploying $SHA (was: ${PREV:-nothing})"
if up "$SHA" && healthy; then
  echo "$SHA" > .deployed
  docker image prune -af --filter "until=168h" >/dev/null   # keep a week of images for rollbacks
  echo "== $SHA is live"
  exit 0
fi

echo "== $SHA is not healthy" >&2
compose ps >&2 || true
compose logs --tail 40 api migrate >&2 || true
if [[ -n "$PREV" ]]; then
  echo "== putting $PREV back" >&2
  up "$PREV"
  healthy && echo "== $PREV is live again" >&2 || echo "== $PREV is not healthy either: look now" >&2
fi
exit 1
