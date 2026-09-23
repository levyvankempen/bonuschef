"""Who gets past the sign-in wall.

The decision is tested without Streamlit, a browser or a cookie, because that
is what has to be right. Whether the form is pretty is not the risk here;
letting the wrong person through, or nobody at all, is.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from bonuschef.portal import gate
from bonuschef.portal.accounts import Account

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "src" / "bonuschef" / "portal" / "app.py"

SOMEONE = Account(
    account_id=2,
    username="levy",
    store_id=1876,
    is_operator=True,
    must_change_password=False,
)


@pytest.fixture
def known(monkeypatch):
    """A token store where exactly one token resolves."""

    def lookup(engine, token, **kw):
        return SOMEONE if token == "good" else None

    monkeypatch.setattr(gate, "account_for_token", lookup)


# --- the wall itself --------------------------------------------------------


def test_a_valid_token_passes(known):
    decision = gate.decide(object(), "good", required=True)
    assert decision.may_pass
    assert decision.account == SOMEONE


def test_an_unknown_token_does_not(known):
    assert not gate.decide(object(), "bad", required=True).may_pass


def test_no_token_does_not(known):
    assert not gate.decide(object(), "", required=True).may_pass


def test_no_token_is_not_looked_up(monkeypatch):
    """Every first page load is this case. It should not cost a query."""
    calls = []
    monkeypatch.setattr(
        gate, "account_for_token", lambda *a, **k: calls.append(a) or None
    )
    gate.decide(object(), "", required=True)
    assert calls == []


# --- the flag ---------------------------------------------------------------


def test_the_wall_is_down_by_default(monkeypatch):
    """A deployment with no account would otherwise become unreachable the
    moment this shipped, and that is the one failure that cannot be fixed from
    inside the application."""
    monkeypatch.delenv("BONUSCHEF_REQUIRE_SIGN_IN", raising=False)
    assert gate.sign_in_required() is False
    assert gate.decide(object(), "").may_pass


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " on "])
def test_the_flag_is_forgiving_about_how_it_is_spelled(monkeypatch, value):
    """An operator typing `true` where the code wanted `1` would leave the
    wall down while believing it up - a silent failure in the direction that
    matters."""
    monkeypatch.setenv("BONUSCHEF_REQUIRE_SIGN_IN", value)
    assert gate.sign_in_required() is True


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "maybe"])
def test_anything_else_leaves_the_wall_down(monkeypatch, value):
    monkeypatch.setenv("BONUSCHEF_REQUIRE_SIGN_IN", value)
    assert gate.sign_in_required() is False


def test_the_flag_decides_whether_there_is_a_wall_not_whether_it_can_be_climbed(known):
    """The distinction that keeps this from being a back door: with the wall
    up, no value of anything lets an unknown token through."""
    for token in ("", "bad", "good "):
        assert not gate.decide(object(), token, required=True).may_pass


# --- where the token is kept ------------------------------------------------


def test_a_token_survives_a_rerun():
    state: dict = {}
    gate.remember(state, "good")
    assert gate.token_from_state(state) == "good"


def test_forgetting_is_not_an_error_when_there_is_nothing_to_forget():
    gate.forget({})


def test_a_missing_cookie_reads_as_no_session(monkeypatch):
    monkeypatch.setattr(
        gate, "_cookie_manager", lambda: SimpleNamespace(get=lambda k: None)
    )
    assert gate.token_from_cookie() == ""


def test_a_broken_cookie_component_does_not_take_the_app_down(monkeypatch):
    """Without a cookie the visitor signs in again, which is a nuisance. An
    exception here would be an outage."""

    def explode():
        raise RuntimeError("component failed to load")

    monkeypatch.setattr(gate, "_cookie_manager", explode)
    assert gate.token_from_cookie() == ""


# --- the wiring, which is the part that makes it structural -----------------


def test_the_gate_precedes_the_navigation():
    """pg.run() is the only thing that executes a page function. With the gate
    above it and ending in st.stop(), a page added to the list inherits the
    guard by being in a list that is never reached."""
    body = APP.read_text()
    assert body.index("gate.decide(") < body.index("st.navigation(")
    assert body.index("st.stop()") < body.index("st.navigation(")


def test_the_gate_stops_the_script_rather_than_hiding_pages():
    """Rendering the sign-in form and carrying on would run every page
    function underneath it."""
    body = APP.read_text()
    guard = body[body.index("if not _gate.may_pass") : body.index("pg = st.navigation")]
    assert "st.stop()" in guard, guard


def test_no_page_checks_authentication_for_itself():
    """A per-page check is one a new page can omit. There should be exactly
    one place that decides."""
    portal = ROOT / "src" / "bonuschef" / "portal"
    for path in portal.glob("*_page.py"):
        body = path.read_text()
        assert "sign_in_required" not in body, path
        assert "gate.decide" not in body, path
