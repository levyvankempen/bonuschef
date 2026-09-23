"""The wall, exercised against a real database and a real Streamlit run.

Marked `warehouse` because it needs Postgres. The decision logic is covered
without a database in test_gate.py; what this adds is the wiring - that the
wall actually stands in front of the pages rather than merely being importable,
and that a correct password takes somebody through it.

This is the test worth having before a login wall is switched on in front of
an application somebody depends on. Everything else is a claim about code; this
is the claim about the product.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from streamlit.testing.v1 import AppTest

from bonuschef.portal.passwords import hash_password
from bonuschef.portal.schema import ensure_account_tables

pytestmark = pytest.mark.warehouse

APP = "src/bonuschef/portal/app.py"
USER = "gate_e2e_user"
PASSWORD = "a-password-for-the-test"


@pytest.fixture
def signed_up(warehouse):
    """An account that can sign in, removed afterwards."""
    ensure_account_tables(warehouse)
    with warehouse.begin() as conn:
        conn.execute(
            text("DELETE FROM public.accounts WHERE username = :u"), {"u": USER}
        )
        conn.execute(
            text("""
                INSERT INTO public.accounts
                    (username, password_hash, store_id, is_operator,
                     must_change_password)
                VALUES (:u, :h, 1876, TRUE, FALSE)
            """),
            {"u": USER, "h": hash_password(PASSWORD)},
        )
    yield
    with warehouse.begin() as conn:
        conn.execute(
            text("DELETE FROM public.accounts WHERE username = :u"), {"u": USER}
        )


def _run(monkeypatch, *, wall: bool) -> AppTest:
    monkeypatch.setenv("BONUSCHEF_REQUIRE_SIGN_IN", "1" if wall else "0")
    app = AppTest.from_file(APP, default_timeout=60)
    app.run()
    return app


def test_with_the_wall_down_nothing_changes(monkeypatch, signed_up):
    """The flag defaults off, and off must mean the application it was before
    the wall existed."""
    app = _run(monkeypatch, wall=False)
    assert [t.value for t in app.title] == ["Vanavond"]


def test_with_the_wall_up_a_stranger_sees_only_the_sign_in(monkeypatch, signed_up):
    app = _run(monkeypatch, wall=True)
    assert [t.value for t in app.title] == ["BonusChef"]
    assert len(app.text_input) >= 2, "a username and a password"


def test_a_wrong_password_is_refused_without_saying_which_half(monkeypatch, signed_up):
    app = _run(monkeypatch, wall=True)
    app.text_input[0].set_value(USER)
    app.text_input[1].set_value("not the password")
    app.button[0].click().run()
    assert [e.value for e in app.error] == ["Gebruikersnaam of wachtwoord klopt niet."]
    assert [t.value for t in app.title] == ["BonusChef"], "still outside"


def test_an_unknown_username_is_refused_identically(monkeypatch, signed_up):
    app = _run(monkeypatch, wall=True)
    app.text_input[0].set_value("nobody-at-all")
    app.text_input[1].set_value("not the password")
    app.button[0].click().run()
    assert [e.value for e in app.error] == ["Gebruikersnaam of wachtwoord klopt niet."]


def test_the_right_password_gets_through(monkeypatch, signed_up):
    app = _run(monkeypatch, wall=True)
    app.text_input[0].set_value(USER)
    app.text_input[1].set_value(PASSWORD)
    app.button[0].click().run()
    assert [t.value for t in app.title] == ["Vanavond"], "should be inside"


# --- throttling, against a real database ------------------------------------


def _attempts(engine, username: str) -> int:
    with engine.begin() as conn:
        return int(
            conn.execute(
                text(
                    "SELECT count(*) FROM public.sign_in_attempts "
                    "WHERE lower(username) = lower(:u)"
                ),
                {"u": username},
            ).scalar()
            or 0
        )


@pytest.fixture
def no_attempts(warehouse):
    ensure_account_tables(warehouse)
    with warehouse.begin() as conn:
        conn.execute(
            text("DELETE FROM public.sign_in_attempts WHERE username = :u"),
            {"u": USER},
        )
    yield warehouse
    with warehouse.begin() as conn:
        conn.execute(
            text("DELETE FROM public.sign_in_attempts WHERE username = :u"),
            {"u": USER},
        )


def test_wrong_passwords_eventually_stop_being_answered(signed_up, no_attempts):
    """Against the real SQL, because the interesting part is the count, and a
    fake engine answers whatever it is told to."""
    from bonuschef.portal.accounts import MAX_FAILURES, sign_in

    for _ in range(MAX_FAILURES):
        assert not sign_in(no_attempts, USER, "wrong").ok
    assert _attempts(no_attempts, USER) == MAX_FAILURES

    blocked = sign_in(no_attempts, USER, PASSWORD)
    assert not blocked.ok, "even the right password waits"
    assert "kwartier" in blocked.error


def test_a_lockout_expires(signed_up, no_attempts):
    """Mutation-driven: the unit test asserted that a cut-off was PASSED to
    the query, which an `OR TRUE` in the WHERE clause satisfied while making
    the lockout permanent. Only real SQL over real rows catches that, and a
    lockout that never expires is an account somebody has destroyed rather
    than protected.
    """
    from bonuschef.portal.accounts import LOCKOUT, MAX_FAILURES, sign_in

    stale = datetime.now(timezone.utc) - LOCKOUT - timedelta(minutes=1)
    with no_attempts.begin() as conn:
        for _ in range(MAX_FAILURES + 3):
            conn.execute(
                text(
                    "INSERT INTO public.sign_in_attempts (username, failed_at) "
                    "VALUES (:u, :t)"
                ),
                {"u": USER, "t": stale},
            )

    assert sign_in(no_attempts, USER, PASSWORD).ok, "old failures must not count"


def test_signing_in_clears_the_record(signed_up, no_attempts):
    from bonuschef.portal.accounts import sign_in

    assert not sign_in(no_attempts, USER, "wrong").ok
    assert _attempts(no_attempts, USER) == 1
    assert sign_in(no_attempts, USER, PASSWORD).ok
    assert _attempts(no_attempts, USER) == 0
