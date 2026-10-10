#!/usr/bin/env bash
# Copy production's data into the test environment.
#
#   ./scripts/copy-to-test.sh
#
# Takes a dump from the production database, restores it into the test one, and
# records when the copy was taken. Production keeps serving throughout.
#
# Why a copy and not a fixture. The defects worth catching before release are
# the ones that only appear against the real catalogue: a recipe whose
# ingredient matched nothing, a shop with no markdowns today, a price that is
# wrong rather than missing. A seeded handful of rows reproduces none of them.
#
# Why pg_dump and not a volume snapshot. A snapshot of a running Postgres data
# directory is a torn file and the restore is a coin toss. pg_dump runs in one
# transaction, which is also what lets production carry on serving.
#
# What this copy contains. Production's accounts - real usernames, real
# password hashes, real saved recipes. Same host, same boundary, not published,
# so the exposure is not new; but it is a second place they live, and that is
# worth knowing rather than discovering. Deliberately not scrubbed: the
# accounts are what make the copy able to reproduce a per-account pricing
# defect, which is most of the point.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

PROD_PROJECT="${BONUSCHEF_PROJECT:-bonuschef}"
TEST_PROJECT="${BONUSCHEF_TEST_PROJECT:-bonuschef-test}"
TEST_ENV_FILE="${BONUSCHEF_TEST_ENV_FILE:-.env.test}"
TEST_COMPOSE="${BONUSCHEF_TEST_COMPOSE:-docker-compose.test.yml}"
KEEP="${BONUSCHEF_KEEP_DUMPS:-3}"
DOCKER="${DOCKER:-docker}"

die() { echo "error: $*" >&2; exit 1; }

[ -f "$TEST_ENV_FILE" ] || die "no ${TEST_ENV_FILE}. Copy .env.test.example and fill it in."

# Where the dumps live. The same directory the test database lives on - the
# SSD - because a 1.1 GB dump beside production's working set on the NVMe is
# avoidable contention, and because the thing that makes a copy repeatable
# without touching production again is keeping the file.
DATA_DIR="$(
    grep -E '^BONUSCHEF_TEST_DATA_DIR=' "$TEST_ENV_FILE" |
        tail -1 | cut -d= -f2- | tr -d '\042\047' || true
)"
[ -n "$DATA_DIR" ] || die "BONUSCHEF_TEST_DATA_DIR is not set in ${TEST_ENV_FILE}"

# The guard that matters.
#
# Everything below runs `DROP SCHEMA` and `pg_restore` against whatever it is
# pointed at, so being pointed at production once is the whole catastrophe.
# Checked on the project name rather than on a host or a port: those are
# variables that get edited, while the project name is what Docker uses to
# decide which containers these are, so it cannot disagree with reality.
[ "$TEST_PROJECT" != "$PROD_PROJECT" ] \
    || die "the target project is ${TEST_PROJECT}, which is production. Refusing."
case "$TEST_PROJECT" in
    *test*) ;;
    *) die "the target project '${TEST_PROJECT}' is not named as a test environment. Refusing." ;;
esac

container_for() {
    # One container of a project's postgres service, by label. Not by name:
    # the names are derived from the project now, precisely so that two stacks
    # can coexist, which means guessing one is how you address the wrong stack.
    "$DOCKER" ps -q \
        --filter "label=com.docker.compose.project=$1" \
        --filter "label=com.docker.compose.service=postgres" | head -1
}

PROD_DB="$(container_for "$PROD_PROJECT")"
[ -n "$PROD_DB" ] || die "production's database is not running; nothing to copy from"

TEST_DB="$(container_for "$TEST_PROJECT")"
if [ -z "$TEST_DB" ]; then
    echo "test database not running; starting it" >&2
    "$DOCKER" compose -f "$TEST_COMPOSE" --env-file "$TEST_ENV_FILE" up -d postgres
    for _ in $(seq 1 60); do
        TEST_DB="$(container_for "$TEST_PROJECT")"
        [ -n "$TEST_DB" ] && "$DOCKER" exec "$TEST_DB" pg_isready -U postgres >/dev/null 2>&1 && break
        sleep 2
    done
    [ -n "$TEST_DB" ] || die "the test database did not start"
fi

# --- get the application off the database -----------------------------------
#
# You cannot restore a database underneath a running application, and this one
# writes SCHEMA, not just rows: the portal applies `ensure_account_tables` from
# its cached engine, and its health probe runs every 30 seconds.
#
# Observed on the first real copy. The restore takes about a minute, the drop
# had already run, and the portal recreated the account tables in the middle of
# it:
#
#   pg_restore: error: could not execute query: ERROR:
#   relation "account_sessions_account_idx" already exists
#
# Stopped rather than paused, and restarted by a trap so that a failed restore
# does not leave the test environment down - the whole point of it is to be
# there when somebody wants to look.
# Compose interpolates at parse time, and the test stack names
# `bonuschef:${BONUSCHEF_VERSION:?}`, so EVERY compose command against that
# file needs the variable - `stop` and `start` included, neither of which
# resolves an image. Without it:
#
#   error while interpolating services.streamlit.image:
#   required variable BONUSCHEF_VERSION is missing a value
#
# This is the same trap scripts/compose.sh exists to absorb for production, and
# the answer is the same: read it off a running container's OCI label.
if [ -z "${BONUSCHEF_VERSION:-}" ]; then
    BONUSCHEF_VERSION="$(
        "$DOCKER" ps -q --filter "label=com.docker.compose.project=${TEST_PROJECT}" \
                       --filter "label=com.docker.compose.service=streamlit" 2>/dev/null |
            head -1 |
            xargs -r "$DOCKER" inspect \
                --format '{{index .Config.Labels "org.opencontainers.image.version"}}' \
                2>/dev/null
    )"
fi
if [ -z "${BONUSCHEF_VERSION:-}" ]; then
    # No test stack running yet: whatever production runs is the right default,
    # since that is the version this copy is being made for.
    BONUSCHEF_VERSION="$(
        "$DOCKER" ps -q --filter "label=com.docker.compose.project=${PROD_PROJECT}" \
                       --filter "label=com.docker.compose.service=streamlit" 2>/dev/null |
            head -1 |
            xargs -r "$DOCKER" inspect \
                --format '{{index .Config.Labels "org.opencontainers.image.version"}}' \
                2>/dev/null
    )"
fi
case "${BONUSCHEF_VERSION:-}" in
    ""|"<no value>"|unknown)
        die "cannot determine which version to run; set BONUSCHEF_VERSION" ;;
esac
export BONUSCHEF_VERSION

compose_test() {
    "$DOCKER" compose -f "$TEST_COMPOSE" --env-file "$TEST_ENV_FILE" "$@"
}

restart_app() {
    compose_test start streamlit >/dev/null 2>&1 || true
}

# Checked, not hoped for.
#
# This was `|| true` with its output discarded, and the stop failed silently on
# the missing variable above - so the restore ran against a live portal and
# died on the index that portal had just recreated. A step the correctness of
# the restore depends on must not be allowed to fail quietly.
echo "stopping the test portal while its database is replaced" >&2
compose_test stop streamlit >&2 \
    || die "could not stop the test portal; refusing to restore underneath it"

# And verified, because the exit status is exactly what was trusted last time.
still_up="$(
    "$DOCKER" ps -q --filter "label=com.docker.compose.project=${TEST_PROJECT}" \
                   --filter "label=com.docker.compose.service=streamlit" 2>/dev/null | wc -l
)"
[ "${still_up:-0}" -eq 0 ] \
    || die "the test portal is still running; it would recreate schema mid-restore"

trap restart_app EXIT

# --- take the dump ----------------------------------------------------------
#
# --format=custom so the restore can drop and recreate rather than replaying
# SQL into whatever is already there, which is what makes this idempotent.
mkdir -p "${DATA_DIR}/dumps"
STAMP="$("$DOCKER" exec "$PROD_DB" date -u +%Y%m%dT%H%M%SZ)"
DUMP="${DATA_DIR}/dumps/production-${STAMP}.dump"

echo "dumping production (it keeps serving)" >&2
"$DOCKER" exec "$PROD_DB" pg_dump -U postgres -d postgres --format=custom --no-owner --no-acl \
    > "$DUMP"
[ -s "$DUMP" ] || die "the dump is empty; refusing to restore it over the test database"
echo "  $(du -h "$DUMP" | cut -f1) -> ${DUMP}" >&2

# --- restore ----------------------------------------------------------------
#
# Drop and recreate the schema first, so restoring over an existing database
# gives the same result as restoring into an empty one. pg_restore --clean
# alone leaves anything the dump does not mention - a table added by a version
# that has since been rolled back, say - which is how a test environment comes
# to hold rows that exist nowhere else.
echo "restoring into ${TEST_PROJECT}" >&2
# Every schema, enumerated rather than listed.
#
# This named `public` and `public_marts`, which is what the portal reads - and
# missed `public_staging`, so the restore failed on `CREATE SCHEMA
# public_staging` with the schema already there. dbt creates one schema per
# model folder, so any hardcoded list is a list that goes stale the next time
# somebody adds a folder.
#
# Safe to be this broad because of the guard at the top: this only ever runs
# against a project whose name is not production's and contains "test".
"$DOCKER" exec -i "$TEST_DB" psql -U postgres -d postgres -v ON_ERROR_STOP=1 -q <<'PSQL'
DO $$
DECLARE victim text;
BEGIN
    FOR victim IN
        SELECT nspname FROM pg_namespace
        WHERE nspname !~ '^pg_' AND nspname <> 'information_schema'
    LOOP
        EXECUTE format('DROP SCHEMA IF EXISTS %I CASCADE', victim);
    END LOOP;
END $$;
CREATE SCHEMA IF NOT EXISTS public;
PSQL

# --no-owner/--no-acl: the roles are not guaranteed to match, and a role error
# aborts a restore that was otherwise fine.
"$DOCKER" exec -i "$TEST_DB" pg_restore -U postgres -d postgres \
    --no-owner --no-acl --exit-on-error < "$DUMP"

# --- record when this copy was taken ----------------------------------------
#
# The copy's age, not the data's. Taking it from the newest row in any data
# table would conflate "this copy is a week old" with "production's pipeline
# was down when I copied", which read identically and mean different things.
#
# Written after the restore, because the restore has just replaced everything.
SOURCE_VERSION="$(
    "$DOCKER" ps -q --filter "label=com.docker.compose.project=${PROD_PROJECT}" \
        --filter "label=com.docker.compose.service=streamlit" | head -1 |
        xargs -r "$DOCKER" inspect \
            --format '{{index .Config.Labels "org.opencontainers.image.version"}}' 2>/dev/null
)"
"$DOCKER" exec -i "$TEST_DB" psql -U postgres -d postgres -v ON_ERROR_STOP=1 -q <<PSQL
CREATE TABLE IF NOT EXISTS public.environment_copy (
    only_row    boolean PRIMARY KEY DEFAULT true CHECK (only_row),
    copied_at   timestamptz NOT NULL,
    source      text,
    dump_file   text
);
INSERT INTO public.environment_copy (only_row, copied_at, source, dump_file)
VALUES (true, now(), '${PROD_PROJECT} ${SOURCE_VERSION:-unknown}', '$(basename "$DUMP")')
ON CONFLICT (only_row) DO UPDATE
    SET copied_at = EXCLUDED.copied_at,
        source    = EXCLUDED.source,
        dump_file = EXCLUDED.dump_file;
PSQL

# --- bound the dumps --------------------------------------------------------
#
# 1.1 GB each. Keeping every copy fills even a 500 GB disk eventually, and the
# only one with a use is the most recent - the older files are a history of
# states nobody will restore.
#
# Said out loud rather than done quietly: a deletion nobody mentioned is one
# nobody can question.
# A `while read` loop rather than `mapfile`: mapfile is bash 4, and this is
# written and tested on macOS, which ships 3.2. A retention policy whose code
# only runs on the deployment host is one nobody has watched work.
while IFS= read -r stale; do
    [ -n "$stale" ] || continue
    echo "removing old dump $(basename "$stale") (keeping ${KEEP})" >&2
    rm -f "$stale"
done < <(ls -1t "${DATA_DIR}/dumps"/production-*.dump 2>/dev/null | tail -n "+$((KEEP + 1))")

# The portal comes back on a database that now has data in it, so its first
# render applies the account schema to the restored copy rather than racing a
# restore.
trap - EXIT
restart_app
echo "test portal restarted" >&2

echo
echo "copied production into ${TEST_PROJECT}"
echo "  dump:   ${DUMP}"
echo "  source: ${PROD_PROJECT} ${SOURCE_VERSION:-unknown}"
echo "the test portal reports this copy's age in its environment banner."
