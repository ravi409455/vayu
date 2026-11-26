#!/usr/bin/env bash
# The local load-test server: production images built from this checkout, pinned to LT_CPUSET.
#   perf/local/stack.sh up [cpuset]      build and start (default cpuset "0" = 1 vCPU)
#   perf/local/stack.sh exec <cmd...>    run a command in the api container
#   perf/local/stack.sh down             stop and delete everything (database and files)
set -euo pipefail
cd "$(dirname "$0")/../.."
export VAYU_TAG=loadtest VAYU_ENV_FILE=perf/local/env
[[ "${1:-}" == up && "${2:-}" =~ ^[0-9][0-9,-]*$ ]] && LT_CPUSET=$2
[[ -z "${LT_CPUSET:-}" && -f "$(dirname "$0")/.cpuset" ]] && LT_CPUSET=$(cat "$(dirname "$0")/.cpuset")
export LT_CPUSET=${LT_CPUSET:-0}
# pushes go to Firebase for real (to fake device tokens): the staging key on this Mac
FIREBASE_JSON=$(find ~/vayu-keys -maxdepth 1 -name "*firebase-adminsdk*.json" 2>/dev/null | head -1)
export FIREBASE_JSON=${FIREBASE_JSON:-/dev/null}
c() { docker compose -f infra/docker-compose.prod.yml -f perf/local/compose.yml --env-file perf/local/env --profile local-db "$@"; }
case "${1:-}" in
  up)
    echo "$LT_CPUSET" > "$(dirname "$0")/.cpuset"
    c build api caddy && c up -d --no-build
    until c exec -T api python -c "1" 2>/dev/null; do sleep 2; done
    docker run --rm --network vayu_default -e AWS_ACCESS_KEY_ID=loadtest \
      -e AWS_SECRET_ACCESS_KEY=loadtest-not-a-secret -e AWS_DEFAULT_REGION=us-east-1 \
      amazon/aws-cli --endpoint-url http://s3:80 s3 mb s3://vayu-loadtest >/dev/null 2>&1 || true
    echo "up on https://localhost, pinned to CPU $LT_CPUSET" ;;
  exec) shift; c exec -T api "$@" ;;
  down) c down -v ;;
  *) c "$@" ;;
esac
