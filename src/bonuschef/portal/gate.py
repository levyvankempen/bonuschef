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

# A cookie write waiting for the end of the run.
_PENDING = "_bonuschef_pending_cookie"

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
    """Hold the token for this connection, and ask for it to outlive it."""
    state[_TOKEN_KEY] = token
    queue_cookie(state, token)


def forget(state) -> None:
    state.pop(_TOKEN_KEY, None)
    queue_cookie(state, "")


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
            st.rerun()
        else:
            st.success("Je account is gemaakt. Meld je aan met je nieuwe naam.")


def render_sign_out(engine) -> None:
    """Offered wherever the signed-in person can see who they are."""
    import streamlit as st

    if st.button("Afmelden", icon=":material/logout:"):
        sign_out(engine, token_from_state(st.session_state))
        forget(st.session_state)
        st.rerun()


def _cookie_manager():
    """One manager per connection.

    Cached in session state because building two in one script run collides on
    the component key, and the failure is a page that renders twice and
    answers neither.
    """
    import extra_streamlit_components as stx
    import streamlit as st

    manager = st.session_state.get("_cookie_manager")
    if manager is None:
        manager = stx.CookieManager(key="bonuschef_cookies")
        st.session_state["_cookie_manager"] = manager
    return manager


def token_from_cookie() -> str:
    """The durable token, read natively rather than through the component.

    st.context.cookies is populated from the websocket upgrade request, so it
    is already there on the first script run of a fresh page load - which is
    exactly the moment a returning visitor needs it.

    The component's own get() is asynchronous: it returns None until the
    frontend answers, and the first run of a page load is precisely when it
    has not. Reading through it meant every reload showed the sign-in form
    before the cookie arrived, which is why signing in felt like it never
    stuck. The component is still what WRITES the cookie; Streamlit cannot.
    """
    import streamlit as st

    try:
        return str(st.context.cookies.get(COOKIE) or "")
    except Exception:  # pragma: no cover - only outside a Streamlit runtime
        return ""


def queue_cookie(state, token: str) -> None:
    """Ask for the cookie to be written at the end of this run.

    Not written here. `set()` renders a component, and the sign-in path calls
    st.rerun() immediately afterwards - which tears the frame down before the
    browser is asked to store anything. Deferring it to after the page has
    rendered is what makes the write actually happen.
    """
    state[_PENDING] = token


def flush_cookie(state) -> None:
    """Perform any queued cookie write. Called once, at the end of a run.

    Failure is reported rather than swallowed. An earlier version caught
    everything and returned quietly, which turned a broken component into
    "you have to sign in every time" with nothing anywhere saying why.
    """
    import streamlit as st

    if _PENDING not in state:
        return
    token = state.pop(_PENDING)
    try:
        if token:
            _cookie_manager().set(COOKIE, token, key="bonuschef_cookie_set")
        else:
            _cookie_manager().delete(COOKIE, key="bonuschef_cookie_del")
    except Exception as exc:  # the app must survive a component that will not
        st.caption(
            ":gray[Je blijft deze sessie aangemeld, maar niet na het "
            "sluiten van het tabblad.]",
            help=f"cookie: {type(exc).__name__}",
        )
