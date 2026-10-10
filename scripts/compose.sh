#!/usr/bin/env bash
# `docker compose`, with the version this stack is running already supplied.
#
#   ./scripts/compose.sh ps
#   ./scripts/compose.sh exec postgres psql -U postgres -d postgres
#   ./scripts/compose.sh logs -f streamlit
#
# Why this exists. The services name `bonuschef:${BONUSCHEF_VERSION:?}` rather
# than building, which is what lets one built image be promoted between
# environments instead of rebuilt. But Compose interpolates at parse time, so
# with the variable unset *every* command fails, including the read-only ones:
#
#   error while interpolating services.dagster-webserver.image:
#   required variable BONUSCHEF_VERSION is missing a value
#
# That is correct for `up` - starting a stack without naming a version is the
# thing being prevented - and pure obstruction for `ps`, `logs` and `exec`,
# which address containers that are already running and resolve no image at
# all. Every documented recovery command is one of those.
#
# So: ask the running stack what it is running, and fall back to the checkout.
# Deliberately not solved by putting the version in .env - the services read
# .env into their environment, so a value that drifted from the image would
# make the portal report a version it is not running, which is the confusion
# the version stamp exists to prevent.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ -z "${BONUSCHEF_VERSION:-}" ]; then
    # What is actually running, read from the OCI label the image carries.
    #
    # The label and not the image tag: before this change the images were named
    # by Compose (`bonuschef-streamlit`), so a tag-parsing version of this
    # would answer nothing on a host that has not deployed since - which is
    # every host, the first time. The label has been stamped all along.
    #
    # And not `git describe` first: the checkout can sit at a different tag
    # than the running stack, and this command is for operating on the stack.
    BONUSCHEF_VERSION="$(
        docker ps --filter "label=com.docker.compose.project=bonuschef" \
                  --format '{{.ID}}' 2>/dev/null | head -1 |
            xargs -r docker inspect \
                --format '{{index .Config.Labels "org.opencontainers.image.version"}}' \
                2>/dev/null
    )" || true
    # An unstamped image answers with the literal label name or an empty
    # string; neither is a version.
    case "${BONUSCHEF_VERSION:-}" in
        ""|"<no value>"|unknown) BONUSCHEF_VERSION="" ;;
    esac
fi

if [ -z "${BONUSCHEF_VERSION:-}" ]; then
    # Nothing running. Fall back to the checkout, so `config` and `pull` work
    # on a host that has never started the stack.
    eval "$(bash ./scripts/version.sh)"
    BONUSCHEF_VERSION="$version"
fi

export BONUSCHEF_VERSION
exec docker compose "$@"
