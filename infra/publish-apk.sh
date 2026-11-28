#!/usr/bin/env bash
# Publish an app build that the "publish app" workflow kept as a GitHub release:
#   infra/publish-apk.sh <tag> <version>      e.g. app-staging-103 0.4.0
# GitHub's locked robot key runs it as "publish-apk <tag> <version>" (infra/deploy.sh passes it on).
# The server downloads the APK from this repository's release itself, so the robot key can only
# publish a build the workflow made (signed with the release key, checked there), never a file it
# is handed. Then manage.py publish_apk stores it in R2 and offers it: the /welcome pages' Download
# and the app's own update offer.
# A staging build (app-staging-*) only goes on a test server, a production build only on production.
# shellcheck source=infra/lib.sh
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

REPO=ravi409455/vayu

[[ $# -eq 2 ]] || die "usage: publish-apk.sh <tag> <version>"
TAG=$1 VERSION=$2
[[ "$TAG" =~ ^app-(staging|production)-([0-9]{1,9})$ ]] || die "tag must be app-staging-<code> or app-production-<code>"
TARGET=${BASH_REMATCH[1]} CODE=${BASH_REMATCH[2]}
[[ "$VERSION" =~ ^[0-9]+(\.[0-9]+){1,3}$ ]] || die "version must look like 0.4.0"

kind=$(envval VAYU_SERVER_KIND)
case "$TARGET" in
  production) [[ "$kind" == production ]] || die "a production build only goes on production (this server: $kind)" ;;
  staging)    [[ "$kind" != production ]] || die "a staging build never goes on production" ;;
esac

tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
url="https://github.com/$REPO/releases/download/$TAG"
echo "== downloading $TAG"
curl -fsSL --max-filesize 200000000 -o "$tmp/vayu.apk" "$url/vayu-$TARGET-$CODE.apk" || die "could not download the APK of release $TAG"
curl -fsSL --max-filesize 10000 -o "$tmp/notes.txt" "$url/notes.txt" || die "could not download the notes of release $TAG"

export VAYU_TAG
VAYU_TAG=$(cat .deployed)
in_api="/tmp/vayu-$CODE.apk"
# piped in (not docker cp): the file then belongs to the app user, who can delete it afterwards
compose exec -T api sh -c "cat > $in_api" < "$tmp/vayu.apk"
rc=0
compose exec -T api python manage.py publish_apk "$in_api" --version-code "$CODE" \
  --version-name "$VERSION" --notes "$(cat "$tmp/notes.txt")" || rc=$?
compose exec -T api rm -f "$in_api"
exit "$rc"
