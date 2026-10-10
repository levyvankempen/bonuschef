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

RUNNER="${BONUSCHEF_RUNNER:-/usr/local/bin/bonuschef-autodeploy}"

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

# The in-flight check below runs `docker compose`, which parses
# docker-compose.yml, which now requires BONUSCHEF_VERSION because the services
# name an image instead of building one. The real version is not known yet - it
# comes from the tag that has not been checked out - and these two commands do
# not care: `ps` and `exec` address containers that are already running, and
# neither resolves an image tag. So a placeholder, replaced with the real value
# before anything is started.
#
# Found by running the deploy path after making the variable mandatory: without
# this the in-flight check fails open, and a deploy would rebuild on top of a
# running Dagster job - the exact thing the check exists to prevent.
export BONUSCHEF_VERSION="${BONUSCHEF_VERSION:-placeholder-for-inspection}"

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

# Start again, from the file this checkout just produced.
#
# Bash reads a script incrementally, so a script that replaces its own file
# mid-run resumes at a byte offset into different content. While deploy.sh was
# identical across releases that was invisible. The release that changed it
# ran as a mixture of both: the old half did `up -d --build` against the new
# docker-compose.yml, which no longer has a build section, so Compose tried to
# *pull* `bonuschef:v1.41.0` from Docker Hub:
#
#   Image bonuschef:v1.41.0 Error pull access denied for bonuschef,
#   repository does not exist or may require 'docker login'
#
# The build step simply was not in the script that was running. Production was
# never at risk - `up` failed and the old containers kept serving - but the
# deploy could not succeed, and would not have on any later tick either while
# the two halves disagreed.
#
# This is the same reasoning that already puts the auto-deploy runner outside
# the checkout: a release must not be able to change the code that is in the
# middle of deploying it. The guard variable stops the re-exec recursing; the
# work repeated before this point is a fetch, a tag check and an in-flight
# query, all of which are cheap and idempotent.
if [ "${BONUSCHEF_DEPLOY_REEXEC:-0}" != "1" ]; then
    export BONUSCHEF_DEPLOY_REEXEC=1
    echo "re-reading deploy.sh from ${TAG}"
    exec bash "$0" "$@"
fi

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

# Build once, then run that image.
#
# This used to be `up -d --build`, which made every host and every deploy build
# independently. Two builds of one commit are not the same bytes, so there was
# no artifact to promote - only source to re-derive. build-image.sh reuses an
# image already tagged for this version, which is what lets a version watched
# working in one environment be the version that runs in another.
# Status checked explicitly, because `eval "$(...)"` cannot report one.
#
# A command substitution's exit status is discarded: `eval "$(false)"` is
# `eval ""`, which succeeds, so `set -e` sees nothing wrong. Written that way,
# a failed build fell straight through to `docker compose up -d`, which found
# no local image and tried to pull one - turning "the build broke" into
# "pull access denied", a message about a registry this project does not use.
if ! build_output="$(bash ./scripts/build-image.sh "$TAG")"; then
    echo "error: the image for ${TAG} could not be built; not starting anything." >&2
    exit 70
fi
eval "$build_output"

if [ -z "${image:-}" ]; then
    echo "error: build-image.sh reported no image for ${TAG}." >&2
    exit 71
fi

# Present locally, before Compose is asked for it. Compose's answer to a
# missing image is to reach for a registry, and the message it produces sends
# the reader looking for credentials rather than for a build failure.
if ! docker image inspect "$image" >/dev/null 2>&1; then
    echo "error: ${image} is not in the local image store." >&2
    echo "Compose would try to pull it, which is not where this image lives." >&2
    exit 72
fi

echo "running ${image}"

docker compose up -d

# Reclaim the build cache this rebuild just produced.
#
# Every build leaves its intermediate layers behind. That was tolerable while
# deploys were occasional and done by hand; with the auto-deploy timer it
# happens on every release, and the cache grew
# to 5.6 GB of a 16 GB rootfs - 100% reclaimable, and larger than the database,
# the images and the logs put together.
#
# Measured on 2026-09-20: 9.3G used -> 5.8G. The Dagster event_logs that
# dagster.yaml worries about were 41 MB, which is to say the disk was filling
# from somewhere nobody was watching.
#
# --filter until=168h, not -a: the last week of cache still speeds up a
# rebuild, and the point is to bound the growth rather than to start cold
# every time. Failure here is not a failed deploy - the stack is already up.
docker builder prune -f --filter until=168h >/dev/null 2>&1 || true
docker image prune -f >/dev/null 2>&1 || true

# Bound the versioned images, which `image prune` cannot touch.
#
# The services used to be built by Compose, which reuses one tag per service -
# `bonuschef-streamlit:latest` and so on - so each build replaced the last and
# the image store never grew. Naming the image by version means every release
# leaves a new 2.6 GB tag behind, and `docker image prune -f` removes only
# DANGLING images, so none of them qualify. Measured right after the change:
# 7.6 GB free before the first deploy, 4.0 GB after. Three more and the rootfs
# is full, which stops Postgres rather than merely stopping deploys.
#
# Two kept by default: the running one, and the one before it so a rollback is
# a tag away rather than a rebuild.
#
# Belt and braces on the running image. `docker rmi` refuses an image in use by
# a container, so this cannot actually delete what is serving - but relying on
# that would make the correctness of this loop depend on Docker's refusal
# rather than on the list being right.
KEEP_IMAGES="${BONUSCHEF_KEEP_IMAGES:-2}"
in_use="$(docker ps --format '{{.Image}}' | sort -u)"
docker images --filter 'reference=bonuschef:v*' \
    --format '{{.CreatedAt}}\t{{.Repository}}:{{.Tag}}' 2>/dev/null |
    sort -r | tail -n "+$((KEEP_IMAGES + 1))" | cut -f2 |
    while IFS= read -r stale; do
        [ -n "$stale" ] || continue
        case "$in_use" in *"$stale"*) continue ;; esac
        echo "removing old image ${stale} (keeping ${KEEP_IMAGES})"
        docker rmi "$stale" >/dev/null 2>&1 || true
    done

# And the images Compose built under its own names, which nothing can reach any
# more: the services name `bonuschef:<version>` now, so these are left over
# from before this change and will never be referenced again.
for legacy in bonuschef-dagster-webserver bonuschef-dagster-daemon bonuschef-streamlit; do
    case "$in_use" in *"$legacy"*) continue ;; esac
    if docker image inspect "${legacy}:latest" >/dev/null 2>&1; then
        echo "removing superseded image ${legacy}:latest"
        docker rmi "${legacy}:latest" >/dev/null 2>&1 || true
    fi
done

# Refresh the auto-deployer's runner, which lives OUTSIDE this checkout.
#
# It used to be run straight from scripts/. That made the deployer part of the
# thing it deploys: roll back to a version predating it and systemd's ExecStart
# points at a file that no longer exists, so auto-deploy stops -- permanently,
# because recovering is precisely what it can no longer do. Observed on a real
# rollback to v1.3.1:
#
#   Unable to locate executable '/opt/bonuschef/scripts/auto-deploy.sh'
#
# Copying it out on every successful deploy keeps it current with the release
# while making it impossible for a release to remove it.
if [ -d "$(dirname "$RUNNER")" ] && [ -w "$(dirname "$RUNNER")" ]; then
    if ! cmp -s ./scripts/auto-deploy.sh "$RUNNER" 2>/dev/null; then
        install -m 0755 ./scripts/auto-deploy.sh "$RUNNER"
        echo "refreshed $RUNNER"
    fi
fi

# And the units themselves, for the same reason one step further on.
#
# The runner was refreshed on every deploy; the systemd files beside it were
# not. So deploy/systemd/ was a committed deployment path that never reached
# the thing it describes: changing the timer's interval in the repository
# changed nothing on the host until somebody remembered to copy it by hand.
# Found by changing that interval and then asking whether it would take effect.
#
# Only on a change, and only when the unit directory is writable - the
# developer case has neither. A daemon-reload while this very service is
# running is safe: systemd applies the new definition at the next start, which
# is the next tick.
UNITS="${BONUSCHEF_SYSTEMD_DIR:-/etc/systemd/system}"
if [ -d "$UNITS" ] && [ -w "$UNITS" ] && [ -d ./deploy/systemd ]; then
    changed=0
    for unit in ./deploy/systemd/bonuschef-*; do
        [ -f "$unit" ] || continue
        if ! cmp -s "$unit" "$UNITS/$(basename "$unit")" 2>/dev/null; then
            install -m 0644 "$unit" "$UNITS/$(basename "$unit")"
            echo "refreshed $UNITS/$(basename "$unit")"
            changed=1
        fi
    done
    if [ "$changed" = 1 ] && command -v systemctl >/dev/null 2>&1; then
        systemctl daemon-reload
        # Restart the timer so a changed interval applies now rather than
        # after the next reboot. The service is deliberately not touched: it
        # is what is running this script.
        systemctl restart bonuschef-autodeploy.timer 2>/dev/null || true
        echo "reloaded systemd units"
    fi
fi

echo
echo "deployed: ${BONUSCHEF_VERSION}"
echo "the portal reports this version in its footer."
