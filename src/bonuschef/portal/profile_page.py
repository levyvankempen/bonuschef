"""Profiel — the settings that belong to a person rather than to the shop.

Today that is which Albert Heijn they read and what their password is. It is
also where food preferences will go, which is why it is a page rather than a
dialog hanging off the sign-in form.

The store lives here and nowhere else. Before accounts it was AH_STORE_ID, an
environment variable read once at startup; a preference read from the
environment cannot differ between two people, and clearance differs by shop.
"""

from __future__ import annotations

import streamlit as st

from bonuschef.portal.accounts import Account, sign_out
from bonuschef.portal.db import (
    get_engine,
    read_account_password_hash,
    read_store_directory,
    set_account_password,
    set_account_store,
)
from bonuschef.portal.gate import forget, token_from_state
from bonuschef.portal.passwords import (
    MIN_LENGTH,
    PasswordTooShort,
    hash_password,
    verify_password,
)

# Parked in session state rather than shown immediately: st.rerun() clears the
# page before a message drawn inside the handler is ever painted.
_SAVED = "_profile_saved"


def render_profile(account: Account) -> None:
    st.title("Profiel")
    engine = get_engine()

    if message := st.session_state.pop(_SAVED, ""):
        st.success(message)

    st.caption(f"Aangemeld als **{account.username}**")

    _render_store(engine, account)
    st.divider()
    _render_password(engine, account)
    st.divider()

    if st.button("Afmelden", icon=":material/logout:"):
        sign_out(engine, token_from_state(st.session_state))
        forget(st.session_state)
        st.rerun()


def _render_store(engine, account: Account) -> None:
    st.subheader("Jouw Albert Heijn")
    st.caption(
        "Laatste kans-koopjes verschillen per winkel. De bonus is overal hetzelfde."
    )

    stores = read_store_directory(engine)
    if not stores:
        st.warning(
            "De winkellijst is nog niet opgehaald. Vraag de beheerder om "
            "deze te vullen."
        )
        return

    ids = [store_id for store_id, _ in stores]
    labels = dict(stores)
    current = account.store_id if account.store_id in ids else None

    chosen = st.selectbox(
        "Winkel",
        options=ids,
        index=ids.index(current) if current is not None else None,
        format_func=lambda i: labels[i],
        placeholder="Kies je winkel",
    )
    if st.button("Winkel opslaan", type="primary", disabled=chosen is None):
        picked = None if chosen is None else int(chosen)
        if picked is not None and set_account_store(engine, account.account_id, picked):
            # The readers are cached per store, so a frame built for the old
            # one would otherwise be served until its TTL ran out.
            st.cache_data.clear()
            st.session_state[_SAVED] = f"Je winkel is nu {labels[picked]}."
            st.rerun()
        else:
            st.error("Die winkel kennen we niet.")


def _render_password(engine, account: Account) -> None:
    st.subheader("Wachtwoord")
    with st.form("change_password"):
        current = st.text_input("Huidig wachtwoord", type="password")
        fresh = st.text_input("Nieuw wachtwoord", type="password")
        again = st.text_input("Nogmaals", type="password")
        submitted = st.form_submit_button("Wachtwoord opslaan", type="primary")

    if not submitted:
        return

    # The current password, first. Without it any unattended browser is an
    # account takeover: the session is already open, so the form would hand
    # the account to whoever is sitting in front of it.
    stored = read_account_password_hash(engine, account.account_id)
    if not verify_password(current, stored):
        st.error("Je huidige wachtwoord klopt niet.")
        return
    if fresh != again:
        st.error("De twee nieuwe wachtwoorden zijn niet gelijk.")
        return
    try:
        hashed = hash_password(fresh)
    except PasswordTooShort:
        st.error(f"Kies er een van minstens {MIN_LENGTH} tekens.")
        return

    set_account_password(engine, account.account_id, hashed)
    st.session_state[_SAVED] = "Je wachtwoord is opgeslagen."
    st.rerun()
