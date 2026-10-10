#!/usr/bin/env bash
# Build the image for a released version, once.
#
#   ./scripts/build-image.sh v1.3.0
#
# Produces `bonuschef:<version>` in the local image store, where <version> is
# what scripts/version.sh derives for the checked-out tree.
#
# Why this exists as a step of its own. Deploying used to be
# `docker compose up -d --build`, which means every environment, and every
# deploy, builds independently. Two builds of one commit are not the same
# artifact - the base image was a floating tag until this change pinned it, and
# anything else unpinned would do the same - so "the version I watched working
# in test" could not be promoted, only re-derived. Building once and running
# that image in both environments is what makes promotion mean something.
#
# Idempotent: an image already tagged for this version is left alone. That is
# the whole point when promoting - production must run the bytes test ran, not
# a rebuild of their source.
#
# Output contract, matching scripts/version.sh: stdout carries exactly one
# `image=` line, so a caller can `eval` it. Progress goes to stderr. Printing
# the progress on stdout instead is how `eval "$(build-image.sh ...)"` comes to
# try running a command called `building`.
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

# A tag, specifically - the same rule deploy.sh applies, for the same reason.
# An image built from a branch is stamped with a name that means something
# different tomorrow.
if ! git rev-parse -q --verify "refs/tags/${TAG}" >/dev/null; then
    echo "error: '${TAG}' is not a tag in this repository." >&2
    echo "Build a released version, not a branch or a bare commit." >&2
    exit 65
fi

# The tag must be what is checked out, not merely a tag that exists.
#
# This script validates the argument and then builds `.`, so without this check
# passing v1.41.0 while sitting on something else succeeds and produces an
# image built from the wrong tree. It would at least be *named* after what was
# actually built - version.sh reports `git describe` - but the argument would
# have been a lie the whole way through, and the deploy that follows would
# promote it.
#
# deploy.sh checks the tag out before calling this, so it passes. Standalone
# use has to check out first, which is the honest cost of not moving somebody's
# HEAD underneath them.
if [ "$(git rev-parse HEAD)" != "$(git rev-parse "refs/tags/${TAG}^{commit}")" ]; then
    echo "error: HEAD is not at ${TAG}, so building here would not build it." >&2
    echo "  git fetch --tags && git checkout --detach refs/tags/${TAG}" >&2
    exit 65
fi

eval "$(bash ./scripts/version.sh)"
IMAGE="${BONUSCHEF_IMAGE:-bonuschef}:${version}"

if [ "${BONUSCHEF_FORCE_BUILD:-0}" != "1" ] \
   && docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "${IMAGE} already built; reusing it" >&2
    echo "image=${IMAGE}"
    exit 0
fi

echo "building ${IMAGE} (${commit:0:12})" >&2
docker build \
    --build-arg "BONUSCHEF_VERSION=${version}" \
    --build-arg "BONUSCHEF_COMMIT=${commit}" \
    -t "$IMAGE" \
    . >&2

echo "image=${IMAGE}"
