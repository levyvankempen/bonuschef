"""The sign-in wall, and the decision about whether to show it.

The decision is separated from the Streamlit parts on purpose. What has to be
right here is *when* somebody is let through, and that is testable without a
browser, a cookie, or a running app. The rendering is the easy half.

## Why this is behind a flag

Turning it on wrongly locks the operator out of their own application, and the
way back in is a database. `BONUSCHEF_REQUIRE_SIGN_IN` lets the wall be
switched on by an operator who has already confirmed they can sign in, and
switched off again by restarting a container rather than by cutting a release.

It is not a bypass: while it is on there is no way past the wall. It decides
whether the wall exists, not whether it can be climbed. It should be removed
once the rollout is done, and there is a task saying so.

## Where the token lives

`st.session_state` first, which survives reruns within one browser connection
and costs nothing to read. A cookie behind it, which survives a reload and a
container restart - the two things session state does not.

Streamlit cannot set a cookie itself: `st.context.cookies` is read-only and is
populated from the websocket upgrade request, so a cookie written any other
way is invisible until the next full page load. Hence the component.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from bonuschef.portal.accounts import Account, account_for_token, sign_in, sign_out
from bonuschef.portal.registration import register, registration_open

# Name of the cookie holding the session token.
COOKIE = "bonuschef_session"

# Where the token lives within one browser connection.
_TOKEN_KEY = "_bonuschef_token"

_FLAG = "BONUSCHEF_REQUIRE_SIGN_IN"


def sign_in_required() -> bool:
    """Whether the wall is up.

    Defaults to off. A deployment that has never created an account would
    otherwise become unreachable the moment this shipped, which is the one
    failure that cannot be fixed from inside the application.
    """
    return os.getenv(_FLAG, "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Gate:
    """What the app should do with this visitor."""

    account: Account | None
    # True when the wall is down: no account, and none needed.
    open_to_everyone: bool = False

    @property
    def may_pass(self) -> bool:
        return self.open_to_everyone or self.account is not None


def decide(engine, token: str, *, required: bool | None = None) -> Gate:
    """Resolve a visitor to an account, or to a reason they cannot pass.

    Pure apart from the session lookup, and the lookup is injected, so the
    rule can be tested without Streamlit.
    """
    required = sign_in_required() if required is None else required
    if not required:
        return Gate(account=None, open_to_everyone=True)
    account = account_for_token(engine, token) if token else None
    return Gate(account=account)


def token_from_state(state) -> str:
    """The token this browser connection is already holding, if any."""
    return str(state.get(_TOKEN_KEY, "") or "")


def remember(state, token: str) -> None:
    state[_TOKEN_KEY] = token


def forget(state) -> None:
    state.pop(_TOKEN_KEY, None)


# ---------------------------------------------------------------------------
# The Streamlit half
# ---------------------------------------------------------------------------


def render_sign_in(engine) -> None:
    """The only thing an unauthenticated visitor sees.

    Dutch, like every other surface here. The refusal deliberately does not
    say which half was wrong.
    """
    import streamlit as st

    st.title("BonusChef")
    with st.form("sign_in"):
        username = st.text_input("Gebruikersnaam")
        password = st.text_input("Wachtwoord", type="password")
        submitted = st.form_submit_button("Aanmelden", type="primary")

    if submitted:
        result = sign_in(engine, username, password)
        if result.ok:
            remember(st.session_state, result.token)
            _write_cookie(result.token)
            st.rerun()
        else:
            st.error(result.error)

    if registration_open():
        _render_register(engine)
    else:
        st.caption("Aanmelden kan alleen op uitnodiging. Vraag het de beheerder.")


def _render_register(engine) -> None:
    """Offered under the sign-in form rather than on a page of its own.

    A separate page would need a route reachable without a session, which is
    the one thing the gate exists to prevent. Folding it in keeps the wall
    with a single opening in it.
    """
    import streamlit as st

    with st.expander("Nog geen account?"):
        with st.form("register"):
            username = st.text_input("Gebruikersnaam", key="reg_username")
            password = st.text_input("Wachtwoord", type="password", key="reg_password")
            again = st.text_input("Nogmaals", type="password", key="reg_again")
            code = st.text_input(
                "Uitnodigingscode",
                type="password",
                key="reg_code",
                help="Die krijg je van de beheerder.",
            )
            submitted = st.form_submit_button("Account maken")

        if not submitted:
            return

        result = register(engine, username, password, again, code)
        if not result.ok:
            st.error(result.error)
            return

        # Signed in straight away. Making somebody type the password they
        # chose two seconds ago is a step that exists only because it was
        # easier to write.
        opened = sign_in(engine, username, password)
        if opened.ok:
            remember(st.session_state, opened.token)
            _write_cookie(opened.token)
            st.rerun()
        else:
            st.success("Je account is gemaakt. Meld je aan met je nieuwe naam.")


def render_sign_out(engine) -> None:
    """Offered wherever the signed-in person can see who they are."""
    import streamlit as st

    if st.button("Afmelden", icon=":material/logout:"):
        sign_out(engine, token_from_state(st.session_state))
        forget(st.session_state)
        _clear_cookie()
        st.rerun()


def _cookie_manager():
    """One manager per connection.

    Constructed lazily and cached in session state: building two of these in
    one script run collides on the component key, and the failure is a page
    that renders twice and answers neither.
    """
    import streamlit as st
    import extra_streamlit_components as stx

    manager = st.session_state.get("_cookie_manager")
    if manager is None:
        manager = stx.CookieManager(key="bonuschef_cookies")
        st.session_state["_cookie_manager"] = manager
    return manager


def token_from_cookie() -> str:
    """The durable token, if the browser has sent one.

    Returns "" both when there is no cookie and when the component has not
    reported yet - they are indistinguishable, and treating the second as "no
    session" is what produces the sign-in form that flashes and then goes
    away. The session-state path above is what usually spares anybody that.
    """
    try:
        return str(_cookie_manager().get(COOKIE) or "")
    except Exception:
        # A component that fails to load must not take the application with
        # it: without a cookie the visitor signs in again, which is a nuisance
        # rather than an outage.
        return ""


def _write_cookie(token: str) -> None:
    try:
        _cookie_manager().set(COOKIE, token, key="bonuschef_cookie_set")
    except Exception:
        pass


def _clear_cookie() -> None:
    try:
        _cookie_manager().delete(COOKIE, key="bonuschef_cookie_del")
    except Exception:
        pass
