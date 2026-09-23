"""The schema the account tables need, applied once at start.

Why this exists separately from the ``ensure_*`` helpers in ``db.py``:

Those are ``CREATE TABLE IF NOT EXISTS`` called lazily from whichever writer
needs the table. That works for adding a table and cannot do the two things
this change needs. It cannot add a column to a table that already holds rows
- ``ah_recipe_verdicts`` needs an account - and it cannot run *before* the
portal starts, which is now required because dbt will read the accounts table
and dbt does not wait for somebody to open a page.

It is also what the portal spec forbids leaning on harder: the portal "SHALL
NOT issue schema-changing statements on each interaction".

Deliberately not Alembic. The ``alembic_version`` table in this Postgres is
**Dagster's** - ``dagster-postgres`` ships its own migrations for run and
event storage into the same database. Pointing a second Alembic at that
schema would have the two fight over one version row, on a host that
auto-deploys every ten minutes. If Alembic is ever adopted here it must be
given its own ``version_table``.

So: an ordered list of statements, each idempotent on its own, applied in
sequence. Re-running is a no-op. The ordering matters only where a foreign
key needs its target to exist first.
"""

from __future__ import annotations

from sqlalchemy import text

# Ordered. Each statement must be safe to run against a database that has
# already had it applied, because that is the normal case - this runs on every
# start, not once.
_STATEMENTS: tuple[str, ...] = (
    # ------------------------------------------------------------------
    # Who is using this
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS public.accounts (
        account_id           BIGSERIAL PRIMARY KEY,
        username             TEXT        NOT NULL,
        password_hash        TEXT        NOT NULL DEFAULT '',
        -- An operator-created account starts with a password the operator
        -- knows, which is not a password the account owner should keep.
        must_change_password BOOLEAN     NOT NULL DEFAULT TRUE,
        -- Nullable on purpose: an account that has not chosen a store must be
        -- asked, never defaulted into somebody else's prices.
        store_id             BIGINT,
        -- Starting a pipeline run and writing shared catalogue state are not
        -- things a guest should be able to do: the run queue holds one slot,
        -- and the hourly clearance scrape is unbackfillable.
        is_operator          BOOLEAN     NOT NULL DEFAULT FALSE,
        created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
        last_sign_in_at      TIMESTAMPTZ
    )
    """,
    # Case-insensitive: "Levy" and "levy" must not be two people, and the
    # sign-in form should not care which one was typed.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS accounts_username_key
        ON public.accounts (lower(username))
    """,
    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS public.account_sessions (
        -- The hash, never the token. A database read must not yield a
        -- working session, for the same reason it must not yield a password.
        token_hash   TEXT        PRIMARY KEY,
        account_id   BIGINT      NOT NULL
            REFERENCES public.accounts (account_id) ON DELETE CASCADE,
        issued_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
        -- Idle expiry is measured against this row rather than against the
        -- cookie, because Streamlit reads cookies only when the websocket
        -- connects and a stale cookie would otherwise never be re-checked.
        last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        revoked_at   TIMESTAMPTZ
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS account_sessions_account_idx
        ON public.account_sessions (account_id)
    """,
    # ------------------------------------------------------------------
    # Albert Heijn credentials
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS public.account_ah_credentials (
        account_id               BIGINT      PRIMARY KEY
            REFERENCES public.accounts (account_id) ON DELETE CASCADE,
        -- Which key encrypted this, so the key can be rotated without
        -- decrypting everything at once.
        key_id                   TEXT        NOT NULL,
        nonce                    BYTEA       NOT NULL,
        ciphertext               BYTEA       NOT NULL,
        -- Carried forward from the bundle rather than re-stamped. It measures
        -- how long a credential value has survived, which is the only
        -- evidence anyone has about how AH expires them.
        refresh_token_issued_at  TIMESTAMPTZ,
        connected_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
        -- The portal has to be able to say when this was last used on the
        -- person's behalf. Nothing records that today.
        last_used_at             TIMESTAMPTZ
    )
    """,
    # ------------------------------------------------------------------
    # What a person records about a shared recipe
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS public.account_recipes (
        account_id   BIGINT      NOT NULL
            REFERENCES public.accounts (account_id) ON DELETE CASCADE,
        recipe_id    BIGINT      NOT NULL,
        saved_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
        -- NULL means never made, which is a different statement from a zero
        -- date and has to be shown differently.
        last_made_at TIMESTAMPTZ,
        notes        TEXT        NOT NULL DEFAULT '',
        PRIMARY KEY (account_id, recipe_id)
    )
    """,
    # ------------------------------------------------------------------
    # Failed sign-in attempts
    # ------------------------------------------------------------------
    #
    # In the database rather than in memory, for two reasons. The portal
    # restarts on every release, and an attacker who can provoke a restart
    # would otherwise clear the count; and a counter held in st.session_state
    # is per browser connection, which is to say per attacker rather than per
    # account.
    #
    # Keyed on the username as typed, not on the account: an account that does
    # not exist must be throttled exactly like one that does, or the throttle
    # becomes the thing that tells you which is which.
    """
    CREATE TABLE IF NOT EXISTS public.sign_in_attempts (
        username   TEXT        NOT NULL,
        failed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS sign_in_attempts_username_idx
        ON public.sign_in_attempts (lower(username), failed_at)
    """,
    # ------------------------------------------------------------------
    # The store directory
    # ------------------------------------------------------------------
    #
    # Cached locally rather than queried per page load. Choosing a store is
    # rare and the list is ~1,200 rows that change about never, so hitting AH
    # every time somebody opens their settings would spend a request on a
    # question whose answer was already known.
    """
    CREATE TABLE IF NOT EXISTS public.ah_stores (
        store_id    BIGINT      PRIMARY KEY,
        name        TEXT        NOT NULL,
        refreshed_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    # ------------------------------------------------------------------
    # Verdicts become personal
    # ------------------------------------------------------------------
    #
    # This is the statement the lazy CREATE-IF-NOT-EXISTS approach cannot
    # express. ah_recipe_verdicts already holds rows, keyed on recipe_id
    # alone, and int_pool_recipes_available excludes anything in it from
    # *everybody's* recommendations. One person's "niet voor mij" currently
    # hides a recipe from all four accounts.
    #
    # Nullable for now: the backfill assigns the existing rows to the operator
    # and only then can this be made NOT NULL, which is a later statement in a
    # later release rather than a column default that would invent an owner.
    """
    ALTER TABLE IF EXISTS public.ah_recipe_verdicts
        ADD COLUMN IF NOT EXISTS account_id BIGINT
    """,
    # The old key was recipe_id alone, which is what made one person's
    # rejection hide a recipe from everybody. Dropping it lets two people
    # disagree; the unique index below keeps one person from rejecting the
    # same recipe twice.
    """
    ALTER TABLE IF EXISTS public.ah_recipe_verdicts
        DROP CONSTRAINT IF EXISTS ah_recipe_verdicts_pkey
    """,
    # Backfilled to 0 rather than left NULL: NULL never equals NULL, so a
    # unique index over it would not stop duplicates, and ON CONFLICT would
    # never fire. 0 is no account, which is what an unattributed verdict is.
    """
    UPDATE public.ah_recipe_verdicts SET account_id = 0 WHERE account_id IS NULL
    """,
    """
    ALTER TABLE IF EXISTS public.ah_recipe_verdicts
        ALTER COLUMN account_id SET NOT NULL
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS ah_recipe_verdicts_account_recipe
        ON public.ah_recipe_verdicts (account_id, recipe_id)
    """,
)


def ensure_account_tables(engine) -> int:
    """Apply the account schema. Safe to run on every start.

    Returns the number of statements executed, so a caller can log it and a
    test can assert the list was not silently truncated.
    """
    with engine.begin() as conn:
        for statement in _STATEMENTS:
            conn.execute(text(statement))
    return len(_STATEMENTS)
