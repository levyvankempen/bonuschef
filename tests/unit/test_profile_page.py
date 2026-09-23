"""Profiel: choosing a shop and changing a password, without a shell.

Run against real Postgres and a real Streamlit script, because the thing worth
proving is that somebody can now do from the page what previously needed ssh.
"""

from pathlib import Path

import pytest
from sqlalchemy import text
from streamlit.testing.v1 import AppTest

from bonuschef.portal.passwords import hash_password, verify_password
from bonuschef.portal.schema import ensure_account_tables

pytestmark = pytest.mark.warehouse

APP = "src/bonuschef/portal/app.py"
USER = "profile_e2e_user"
PASSWORD = "a-password-for-the-test"
STORE = 1876
OTHER_STORE = 1661


@pytest.fixture
def account(warehouse):
    ensure_account_tables(warehouse)
    with warehouse.begin() as conn:
        conn.execute(
            text("DELETE FROM public.accounts WHERE username = :u"), {"u": USER}
        )
        for store_id, name in (
            (STORE, "Eindhoven Torenallee"),
            (OTHER_STORE, "Eindhoven Kamperfoelielaan"),
        ):
            conn.execute(
                text("""
                    INSERT INTO public.ah_stores (store_id, name) VALUES (:i, :n)
                    ON CONFLICT (store_id) DO UPDATE SET name = EXCLUDED.name
                """),
                {"i": store_id, "n": name},
            )
        conn.execute(
            text("""
                INSERT INTO public.accounts
                    (username, password_hash, store_id, is_operator,
                     must_change_password)
                VALUES (:u, :h, NULL, FALSE, FALSE)
            """),
            {"u": USER, "h": hash_password(PASSWORD)},
        )
    yield warehouse
    with warehouse.begin() as conn:
        conn.execute(
            text("DELETE FROM public.accounts WHERE username = :u"), {"u": USER}
        )


def _signed_in(monkeypatch) -> AppTest:
    monkeypatch.setenv("BONUSCHEF_REQUIRE_SIGN_IN", "1")
    app = AppTest.from_file(APP, default_timeout=60)
    app.run()
    app.text_input[0].set_value(USER)
    app.text_input[1].set_value(PASSWORD)
    app.button[0].click().run()
    return app


def _stored(engine, column: str):
    with engine.begin() as conn:
        return conn.execute(
            text(f"SELECT {column} FROM public.accounts WHERE username = :u"),
            {"u": USER},
        ).scalar()


def test_an_account_with_no_shop_is_asked_before_anything_else(monkeypatch, account):
    """Not defaulted. Clearance is scoped to a store, so filling one in
    silently is how one person's prices become everybody's."""
    app = _signed_in(monkeypatch)
    assert [t.value for t in app.title] == ["Profiel"]
    assert not app.selectbox[0].value, "nothing preselected"


def test_choosing_a_shop_lets_the_app_through(monkeypatch, account):
    app = _signed_in(monkeypatch)
    app.selectbox[0].set_value(STORE).run()
    app.button[0].click().run()
    assert _stored(account, "store_id") == STORE
    assert [t.value for t in app.title] == ["Vanavond"], "should be inside now"


def test_changing_the_shop_clears_the_cached_frames():
    """The readers are cached per store. Without clearing, a frame built for
    the old shop is served until its TTL runs out - so the setting appears to
    have been ignored."""
    page = Path("src/bonuschef/portal/profile_page.py").read_text()
    save = page[
        page.index("set_account_store(engine") : page.index("def _render_password")
    ]
    assert "st.cache_data.clear()" in save, save


def test_the_password_form_checks_the_current_one_first():
    """Without it any unattended browser is an account takeover: the session
    is already open, so the form hands the account to whoever is sitting
    there. A source check, because reaching this form under AppTest means
    navigating a function-based page, which AppTest cannot address."""
    page = Path("src/bonuschef/portal/profile_page.py").read_text()
    body = page[page.index("def _render_password") :]
    assert body.index("verify_password") < body.index("set_account_password")


def test_a_new_password_replaces_the_old_one_and_clears_the_flag(account):
    """The two go together: an account that has chosen its own password is no
    longer holding one the operator knows."""
    from bonuschef.portal.db import read_account_password_hash, set_account_password

    account_id = _stored(account, "account_id")
    with account.begin() as conn:
        conn.execute(
            text(
                "UPDATE public.accounts SET must_change_password = TRUE "
                "WHERE username = :u"
            ),
            {"u": USER},
        )
    set_account_password(account, int(account_id), hash_password("a-brand-new-one"))

    stored = read_account_password_hash(account, int(account_id))
    assert verify_password("a-brand-new-one", stored)
    assert not verify_password(PASSWORD, stored), "the old one must stop working"
    assert _stored(account, "must_change_password") is False


def test_an_unknown_shop_is_refused(account):
    """An id nobody recognises reads another town's clearance with nothing on
    the page to reveal it."""
    from bonuschef.portal.db import set_account_store

    account_id = int(_stored(account, "account_id"))
    assert set_account_store(account, account_id, 999999) is False
    assert _stored(account, "store_id") is None, "and nothing was written"
