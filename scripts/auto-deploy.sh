#!/usr/bin/env bash
# Deploy the newest release, if it is newer than what is running.
#
# Run from a systemd timer. This is the pull half of GitOps: the desired state
# is "the newest tag in the repository", and this reconciles towards it.
#
# It is deliberately quiet. A tick with nothing to do, and a tick that declines
# to act, both exit 0 -- a timer that reports failure for "a Dagster run is in
# progress" would cry wolf several times a day and be muted within a week.
# Only a genuine deployment failure is an error.
set -euo pipefail

# Where the deployment lives.
#
# This script is installed to /usr/local/bin so that a rollback cannot delete
# systemd's ExecStart target. That means it can no longer assume it sits
# inside the checkout it operates on: resolving its own directory from
# /usr/local/bin lands in /usr/local, and the first git command fails with
# "not a git repository". Which is exactly what happened on the server.
#
# Prefer a checkout next to the script - that is the developer case, and the
# one the tests exercise - and fall back to the installed location.
_here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if git -C "$_here" rev-parse --git-dir >/dev/null 2>&1; then
    cd "$_here"
else
    cd "${BONUSCHEF_CHECKOUT:-/opt/bonuschef}"
fi

log() { echo "[auto-deploy] $*"; }

# Someone debugging on the box has edited files in place. Deploying would
# discard their work with `git checkout --detach`, which is a rude thing to do
# to a person who is mid-investigation.
if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    log "working tree is not clean; leaving it alone"
    git status --short | sed 's/^/  /'
    exit 0
fi

# --prune-tags, not just --prune: the latter only prunes remote-tracking
# branches. Without it a tag that exists only on this box -- created by hand,
# or left by a tag deleted upstream -- would still be listed locally and could
# be picked as "the newest release". Upstream is the authority on what has
# been released.
git fetch --tags --prune --prune-tags --quiet origin

# Newest release tag by version order, not by date: a patch cut for an older
# line would otherwise look newer than the release it is behind.
latest="$(git tag --list 'v*' --sort=-v:refname | head -1)"
if [ -z "$latest" ]; then
    log "no release tags found"
    exit 0
fi

current="$(git describe --tags --exact-match HEAD 2>/dev/null || echo none)"

if [ "$current" = "$latest" ]; then
    log "up to date ($current)"
    exit 0
fi

# `current` is "none" when HEAD sits at no known tag: a hand-made commit on the
# box, or a tag that has since been deleted upstream. Deploying the newest
# release is the right recovery -- it is what reconciling towards the declared
# state means -- and the dirty-tree check above has already protected anyone
# who is mid-investigation.

log "deploying $latest (was $current)"

set +e
./scripts/deploy.sh "$latest"
status=$?
set -e

case "$status" in
    0)
        log "deployed $latest"
        ;;
    75)
        # deploy.sh refused because a Dagster run is in flight. Rebuilding
        # would kill the run worker without Dagster noticing, wedging the
        # queue. Waiting for the next tick is the correct behaviour, not a
        # failure.
        log "a run is in flight; will retry on the next tick"
        exit 0
        ;;
    *)
        log "deploy of $latest failed with status $status"
        exit "$status"
        ;;
esac
