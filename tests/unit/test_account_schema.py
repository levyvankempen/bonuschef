"""The account schema and the backfill that attributes existing rows to it.

These run on a database that has been in use for months, so the tests are
mostly about what must NOT happen.
"""

from contextlib import contextmanager
from pathlib import Path

import pytest

from bonuschef.portal import schema

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / "scripts" / "bootstrap_accounts.py"


class RecordingEngine:
    """Records the SQL it is handed. No database, by design."""

    def __init__(self):
        self.statements: list[str] = []

    @contextmanager
    def begin(self):
        yield self

    def execute(self, statement, params=None):
        self.statements.append(str(statement).strip())
        return None


def _columns(statement: str) -> list[str]:
    """The column definitions, with SQL comments removed.

    The comments matter here: collapsing this SQL onto one line would make a
    trailing `--` comment swallow the column after it, so the stripping has to
    happen per line, before anything is joined.
    """
    lines = [
        line.split("--", 1)[0].strip()
        for line in statement.splitlines()
        if line.split("--", 1)[0].strip()
    ]
    return [part.strip() for part in " ".join(lines).split(",")]


@pytest.fixture
def applied() -> list[str]:
    engine = RecordingEngine()
    schema.ensure_account_tables(engine)
    return engine.statements


# --- idempotency ------------------------------------------------------------


def test_every_statement_is_idempotent(applied):
    """This runs on every start, not once. A statement that fails the second
    time takes the portal down on the first restart after a deploy - which,
    with auto-deploy, is within ten minutes of merging."""
    for statement in applied:
        assert "IF NOT EXISTS" in statement or "IF EXISTS" in statement, statement


def test_applying_twice_produces_the_same_statements():
    first, second = RecordingEngine(), RecordingEngine()
    schema.ensure_account_tables(first)
    schema.ensure_account_tables(second)
    assert first.statements == second.statements


def test_it_reports_how_much_it_applied():
    """So a truncated list is visible rather than silent."""
    engine = RecordingEngine()
    assert schema.ensure_account_tables(engine) == len(engine.statements)


# --- what the lazy CREATE-IF-NOT-EXISTS approach cannot do ------------------


def test_verdicts_gain_an_account_by_alter(applied):
    """ah_recipe_verdicts already holds rows. A CREATE TABLE IF NOT EXISTS
    would silently do nothing, and the column would never arrive."""
    alters = [s for s in applied if s.lstrip().startswith("ALTER TABLE")]
    assert any("ah_recipe_verdicts" in s and "account_id" in s for s in alters), alters


def test_the_verdict_column_is_nullable(applied):
    """The existing rows have no owner until the backfill gives them one. A
    NOT NULL with a default would invent one."""
    alter = next(s for s in applied if "ah_recipe_verdicts" in s)
    assert "NOT NULL" not in " ".join(
        line.split("--", 1)[0] for line in alter.splitlines()
    ), alter


# --- shape -----------------------------------------------------------------


def test_deleting_an_account_takes_its_rows_with_it(applied):
    """Leaving a friend's sessions and credentials behind after their account
    is gone is the failure that makes 'disconnect' untrue."""
    owned = [s for s in applied if "REFERENCES public.accounts" in s]
    assert len(owned) >= 3, owned
    for statement in owned:
        assert "ON DELETE CASCADE" in statement, statement


def test_a_store_is_not_defaulted(applied):
    """An account with no store must be asked, never filled in from somebody
    else's prices. A DEFAULT here would do exactly that."""
    accounts = next(
        s for s in applied if "CREATE TABLE IF NOT EXISTS public.accounts" in s
    )
    store_clause = next(
        part for part in _columns(accounts) if part.startswith("store_id")
    )
    assert "DEFAULT" not in store_clause, store_clause


def test_usernames_collide_case_insensitively(applied):
    """ "Levy" and "levy" must not be two people."""
    assert any("lower(username)" in s and "UNIQUE" in s for s in applied), applied


def test_sessions_store_a_hash_not_a_token(applied):
    """A database read must not yield a working session, for the same reason
    it must not yield a password."""
    sessions = next(s for s in applied if "account_sessions" in s and "CREATE" in s)
    assert "token_hash" in sessions
    assert "token TEXT" not in sessions


def test_a_credential_records_when_it_was_last_used(applied):
    """The spec requires telling a person when their shop account was last
    used on their behalf. Nothing records that today."""
    creds = next(s for s in applied if "account_ah_credentials" in s and "CREATE" in s)
    assert "last_used_at" in creds


def test_a_credential_keeps_its_issue_date(applied):
    """That timestamp measures how long a credential value has survived, and
    it is the only evidence there is about how AH expires tokens from disuse.
    Re-stamping it on migration would destroy the series."""
    creds = next(s for s in applied if "account_ah_credentials" in s and "CREATE" in s)
    assert "refresh_token_issued_at" in creds


def test_a_credential_names_the_key_that_encrypted_it(applied):
    """Without it the key cannot be rotated without decrypting everything at
    once, which means it never gets rotated."""
    creds = next(s for s in applied if "account_ah_credentials" in s and "CREATE" in s)
    assert "key_id" in creds


def test_never_made_is_distinguishable_from_never_recorded(applied):
    saved = next(s for s in applied if "account_recipes" in s and "CREATE" in s)
    last_made = next(
        part for part in _columns(saved) if part.startswith("last_made_at")
    )
    assert "NOT NULL" not in last_made, last_made


# --- the backfill ----------------------------------------------------------


def test_the_backfill_leaves_resolutions_alone():
    """Roughly 1900 concept-to-product links, 86 of them confirmed by hand,
    each having cost a search against AH. They are facts about the catalogue,
    so scoping them to an account would hand every new person an unpriceable
    catalogue and ask them to redo work already done."""
    body = BOOTSTRAP.read_text()
    writes = [
        line
        for line in body.splitlines()
        if any(
            verb in line.upper() for verb in ("INSERT INTO", "UPDATE ", "DELETE FROM")
        )
    ]
    assert writes, "the backfill is supposed to write something"
    assert not any("ah_ingredient_products" in w for w in writes), writes


def test_the_backfill_says_what_it_skipped():
    """A skipped table that is never mentioned reads as an oversight later."""
    assert "untouched" in BOOTSTRAP.read_text()


def test_the_backfill_is_rerunnable():
    """It will be run on a rehearsal restore and then on the real database."""
    body = BOOTSTRAP.read_text()
    assert "ON CONFLICT" in body
    assert "account_id IS NULL" in body, "verdicts would be re-claimed every run"


def test_the_backfill_offers_a_dry_run():
    assert "--dry-run" in BOOTSTRAP.read_text()


def test_the_store_is_seeded_from_the_existing_configuration():
    """The markdown history already carries store_id 1876. An operator account
    with a different store would orphan it."""
    assert "AH_STORE_ID" in BOOTSTRAP.read_text()
