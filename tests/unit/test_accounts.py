"""Signing in, staying signed in, and stopping being signed in.

No database. The SQL is exercised against the warehouse elsewhere; what is
pinned here is the decisions - what is stored, what is refused, and when a
session stops counting.

Time is injected throughout, because every rule here is about expiry and a
test that waits out a real clock either sleeps or asserts nothing.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from bonuschef.portal import accounts
from bonuschef.portal.accounts import (
    IDLE_LIFETIME,
    account_for_token,
    sign_in,
    sign_out,
    token_hash,
)
from bonuschef.portal.passwords import KdfParams, hash_password

CHEAP = KdfParams(n=2**10, r=8, p=1)
T0 = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _fast_hashing(monkeypatch):
    from bonuschef.portal import passwords

    monkeypatch.setattr(passwords, "DEFAULT_PARAMS", CHEAP)
    # The dummy hash is built at import time at production cost. Left alone it
    # would make every failed-sign-in test spend 200ms proving a point the
    # timing test already makes by reading the source.
    monkeypatch.setattr(
        accounts, "_DUMMY_HASH", hash_password("dummy value", params=CHEAP)
    )


class FakeEngine:
    """Answers queries from a queue and records what it was asked.

    `failures` is what the throttle counter sees. It is answered separately
    from the row queue because the count is asked first on every sign-in, and
    letting it consume a queued row made every test one row out of step.
    """

    def __init__(self, *rows, failures: int = 0):
        self.rows = list(rows)
        self.failures = failures
        self.statements: list[str] = []
        self.params: list[dict] = []

    @contextmanager
    def begin(self):
        yield self

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.statements.append(sql)
        self.params.append(params or {})
        if "count(*) FROM public.sign_in_attempts" in sql:
            return SimpleNamespace(scalar=lambda: self.failures, fetchone=lambda: None)
        row = self.rows.pop(0) if self.rows else None
        return SimpleNamespace(fetchone=lambda: row, scalar=lambda: None)

    def wrote(self, fragment: str) -> bool:
        return any(fragment in s for s in self.statements)


def _account_row(password: str, **over):
    fields = {
        "account_id": 1,
        "username": "levy",
        "password_hash": hash_password(password, params=CHEAP),
        "store_id": 1876,
        "is_operator": True,
        "must_change_password": False,
    }
    fields.update(over)
    return SimpleNamespace(**fields)


def _session_row(last_seen=T0, revoked=None, **over):
    fields = {
        "account_id": 1,
        "last_seen_at": last_seen,
        "revoked_at": revoked,
        "username": "levy",
        "store_id": 1876,
        "is_operator": True,
        "must_change_password": False,
    }
    fields.update(over)
    return SimpleNamespace(**fields)


# --- signing in -------------------------------------------------------------


def test_the_right_password_opens_a_session():
    engine = FakeEngine(_account_row("correct horse battery"))
    result = sign_in(engine, "levy", "correct horse battery", now=lambda: T0)
    assert result.ok
    assert result.account is not None
    assert result.account.account_id == 1
    assert result.token


def test_the_token_is_not_what_gets_stored():
    """A database read must not yield a working session."""
    engine = FakeEngine(_account_row("correct horse battery"))
    result = sign_in(engine, "levy", "correct horse battery", now=lambda: T0)
    stored = [p.get("token_hash") for p in engine.params if "token_hash" in p]
    assert stored, engine.statements
    assert result.token not in stored
    assert token_hash(result.token) in stored


def test_a_wrong_password_is_refused():
    engine = FakeEngine(_account_row("correct horse battery"))
    result = sign_in(engine, "levy", "wrong", now=lambda: T0)
    assert not result.ok
    assert not result.token


def test_an_unknown_user_gets_the_same_answer_as_a_wrong_password():
    """Otherwise the form is a way to find out who has an account."""
    known = FakeEngine(_account_row("correct horse battery"))
    unknown = FakeEngine(None)
    a = sign_in(known, "levy", "wrong", now=lambda: T0)
    b = sign_in(unknown, "nobody", "wrong", now=lambda: T0)
    assert a.error == b.error != ""


def test_an_unknown_user_still_costs_a_verification():
    """A message that matches while the timing does not is half a defence.
    Returning early for an unknown username makes it measurably faster than a
    wrong password."""
    import inspect

    source = inspect.getsource(sign_in)
    head = source.split("if row is None:")[1].split("return")[0]
    assert "verify_password" in head, head


def test_no_session_is_opened_for_a_failed_sign_in():
    engine = FakeEngine(_account_row("correct horse battery"))
    sign_in(engine, "levy", "wrong", now=lambda: T0)
    assert not engine.wrote("INSERT INTO public.account_sessions")


def test_the_username_is_matched_without_regard_to_case():
    engine = FakeEngine(_account_row("correct horse battery"))
    sign_in(engine, "  LEVY ", "correct horse battery", now=lambda: T0)
    assert engine.wrote("lower(username) = lower(:username)")
    lookup = next(p for p in engine.params if "username" in p)
    assert lookup["username"] == "LEVY", "surrounding space is not a username"


# --- staying signed in ------------------------------------------------------


def test_a_live_session_resolves_to_its_account():
    engine = FakeEngine(_session_row(last_seen=T0))
    account = account_for_token(engine, "tok", now=lambda: T0 + timedelta(hours=1))
    assert account is not None
    assert account.username == "levy"


def test_using_a_session_keeps_it_alive():
    """Idle expiry, not absolute. Someone who opens the app daily should not
    be signed out on a schedule."""
    engine = FakeEngine(_session_row(last_seen=T0))
    account_for_token(engine, "tok", now=lambda: T0 + timedelta(days=13))
    assert engine.wrote("SET last_seen_at = :stamp")


def test_an_idle_session_stops_counting():
    engine = FakeEngine(_session_row(last_seen=T0))
    assert (
        account_for_token(
            engine, "tok", now=lambda: T0 + IDLE_LIFETIME + timedelta(minutes=1)
        )
        is None
    )


def test_an_expired_session_is_not_refreshed():
    """Touching last_seen_at on the way to refusing would make the session
    immortal: every attempt would reset the clock it just failed."""
    engine = FakeEngine(_session_row(last_seen=T0))
    account_for_token(engine, "tok", now=lambda: T0 + IDLE_LIFETIME * 2)
    assert not engine.wrote("SET last_seen_at = :stamp")


def test_a_revoked_session_is_refused():
    engine = FakeEngine(_session_row(revoked=T0))
    assert (
        account_for_token(engine, "tok", now=lambda: T0 + timedelta(minutes=1)) is None
    )


def test_an_unknown_token_is_refused():
    assert account_for_token(FakeEngine(None), "tok", now=lambda: T0) is None


def test_no_token_asks_the_database_nothing():
    """The signed-out case is every first page load. It should not cost a
    query."""
    engine = FakeEngine()
    assert account_for_token(engine, "", now=lambda: T0) is None
    assert engine.statements == []


def test_a_naive_timestamp_is_read_as_utc():
    """Postgres can hand back a naive datetime depending on the column and the
    driver. Subtracting one from an aware `now` raises, and the failure would
    be a sign-in loop rather than an error anyone sees."""
    engine = FakeEngine(_session_row(last_seen=T0.replace(tzinfo=None)))
    assert account_for_token(engine, "tok", now=lambda: T0 + timedelta(hours=1))


# --- signing out ------------------------------------------------------------


def test_signing_out_revokes_the_session():
    engine = FakeEngine()
    sign_out(engine, "tok", now=lambda: T0)
    assert engine.wrote("SET revoked_at = :stamp")


def test_signing_out_twice_is_not_an_error():
    engine = FakeEngine()
    sign_out(engine, "tok", now=lambda: T0)
    assert engine.wrote("revoked_at IS NULL"), "a second sign-out must not re-stamp"


def test_signing_out_without_a_token_does_nothing():
    engine = FakeEngine()
    sign_out(engine, "", now=lambda: T0)
    assert engine.statements == []


# --- throttling -------------------------------------------------------------


def test_a_failed_attempt_is_recorded():
    engine = FakeEngine(_account_row("correct horse battery"))
    sign_in(engine, "levy", "wrong", now=lambda: T0)
    assert engine.wrote("INSERT INTO public.sign_in_attempts")


def test_a_successful_attempt_is_not():
    engine = FakeEngine(_account_row("correct horse battery"))
    sign_in(engine, "levy", "correct horse battery", now=lambda: T0)
    assert not engine.wrote("INSERT INTO public.sign_in_attempts")


def test_enough_failures_stop_the_attempts():
    engine = FakeEngine(
        _account_row("correct horse battery"), failures=accounts.MAX_FAILURES
    )
    result = sign_in(engine, "levy", "correct horse battery", now=lambda: T0)
    assert not result.ok, "even the right password waits"
    assert result.error != accounts._REFUSED, "and says why"


def test_a_throttled_attempt_does_not_check_the_password():
    """So a locked account costs nothing to refuse, and cannot be used to
    measure whether a password was close."""
    engine = FakeEngine(
        _account_row("correct horse battery"), failures=accounts.MAX_FAILURES
    )
    sign_in(engine, "levy", "correct horse battery", now=lambda: T0)
    assert not engine.wrote("FROM public.accounts")


def test_one_short_of_the_limit_still_tries():
    engine = FakeEngine(
        _account_row("correct horse battery"), failures=accounts.MAX_FAILURES - 1
    )
    assert sign_in(engine, "levy", "correct horse battery", now=lambda: T0).ok


def test_the_count_only_looks_at_recent_failures():
    """A lockout that never expires is an account somebody has destroyed
    rather than protected."""
    engine = FakeEngine(_account_row("correct horse battery"))
    sign_in(engine, "levy", "wrong", now=lambda: T0)
    counted = next(p for p in engine.params if "since" in p)
    assert counted["since"] == T0 - accounts.LOCKOUT


def test_a_correct_password_ends_the_lockout():
    """Otherwise somebody who mistyped five times and then remembered it is
    still shut out, which punishes the person this protects."""
    engine = FakeEngine(_account_row("correct horse battery"))
    sign_in(engine, "levy", "correct horse battery", now=lambda: T0)
    assert engine.wrote("DELETE FROM public.sign_in_attempts")


def test_an_unknown_username_is_throttled_too():
    """Otherwise the throttle is the thing that tells you which usernames
    exist: one answers instantly forever, the other stops."""
    engine = FakeEngine(None)
    sign_in(engine, "nobody", "wrong", now=lambda: T0)
    assert engine.wrote("INSERT INTO public.sign_in_attempts")
