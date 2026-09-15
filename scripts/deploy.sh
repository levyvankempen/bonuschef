#!/usr/bin/env bash
# Deploy a released version.
#
#   ./scripts/deploy.sh v1.3.0
#
# Run on the deployment host, in the checkout at /opt/bonuschef.
#
# This replaces rsyncing a working tree, which is how the guest ended up
# running code nobody could identify -- docs/deployment.md records one such
# deployment carrying 33 unpushed commits.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

TAG="${1:-}"
if [ -z "$TAG" ]; then
    echo "usage: $0 <tag>    (e.g. $0 v1.3.0)" >&2
    echo >&2
    echo "available:" >&2
    git tag --sort=-v:refname 2>/dev/null | head -5 | sed 's/^/  /' >&2
    exit 64
fi

git fetch --tags --prune origin

# A tag, specifically. Deploying a branch is how you get back to not knowing
# what is running: `main` means something different tomorrow, and the stamp
# baked into the image would describe a moving target.
if ! git rev-parse -q --verify "refs/tags/${TAG}" >/dev/null; then
    echo "error: '${TAG}' is not a tag in this repository." >&2
    echo "Deploy a released version, not a branch or a bare commit." >&2
    exit 65
fi

# Rebuilding kills the run worker's process, and Dagster does not notice: the
# run stays STARTED, holds its concurrency slot, and the queue stalls until
# run monitoring times it out. Learned the hard way; see docs/deployment.md.
if docker compose ps --status running --quiet dagster-webserver >/dev/null 2>&1; then
    in_flight="$(docker compose exec -T dagster-webserver python - <<'PY' 2>/dev/null || echo 0
import json, urllib.request
q = '{runsOrError(filter:{statuses:[STARTED,STARTING]}){... on Runs{results{runId}}}}'
try:
    r = urllib.request.urlopen(urllib.request.Request(
        "http://localhost:3000/graphql",
        data=json.dumps({"query": q}).encode(),
        headers={"Content-Type": "application/json"}), timeout=10)
    print(len(json.loads(r.read())["data"]["runsOrError"]["results"]))
except Exception:
    print(0)
PY
)"
    if [ "${in_flight:-0}" -gt 0 ]; then
        echo "error: ${in_flight} run(s) in flight. Rebuilding now wedges the queue." >&2
        echo "Wait for them to finish, or terminate them in the Dagster UI." >&2
        exit 75
    fi
fi

git checkout -q --detach "refs/tags/${TAG}"

# .env is untracked and stays put. It is the one thing on this host that
# cannot be recreated from the repository.
if [ ! -f .env ]; then
    echo "error: no .env in $(pwd). Refusing to start with defaults." >&2
    exit 78
fi

# Invoked through bash rather than as ./scripts/version.sh: relying on the
# mode bit means a lost +x surfaces as "version: unbound variable" three lines
# later instead of as a plain failure here.
eval "$(bash ./scripts/version.sh)"
export BONUSCHEF_VERSION="$version" BONUSCHEF_COMMIT="$commit"
echo "deploying ${BONUSCHEF_VERSION} (${BONUSCHEF_COMMIT:0:12})"

docker compose up -d --build

echo
echo "deployed: ${BONUSCHEF_VERSION}"
echo "the portal reports this version in its footer."
