#!/usr/bin/env bash
# Derive the version and commit an image should be stamped with.
#
# Prints two lines, `version=` and `commit=`, for a caller to read with
# `eval` or pass on as build args.
#
# `git describe --tags --always --dirty` is what makes a modified tree
# distinguishable from the release it resembles:
#
#   v1.3.0                      exactly at the tag
#   v1.3.0-5-gabc1234           five commits past it
#   v1.3.0-5-gabc1234-dirty     ...with uncommitted changes
#   abc1234                     no tags reachable yet
#
# Reading the version out of pyproject.toml instead would report `1.3.0` for
# all four, which is the confusion this exists to prevent.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if git rev-parse --git-dir >/dev/null 2>&1; then
    version="$(git describe --tags --always --dirty 2>/dev/null || echo unknown)"
    commit="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
    if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
        # `describe --dirty` only notices tracked modifications, and only when
        # a tag is reachable. An untracked file, or a repository with no tags
        # at all, would otherwise be stamped as if it were clean.
        case "$version" in
            *-dirty) ;;
            *) version="${version}-dirty" ;;
        esac
    fi
else
    # A tarball or a CI archive with no history. Fall back to the packaged
    # version, which is honest about being a guess at provenance.
    version="$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml | head -1)"
    version="${version:-unknown}-nogit"
    commit="unknown"
fi

echo "version=${version}"
echo "commit=${commit}"
