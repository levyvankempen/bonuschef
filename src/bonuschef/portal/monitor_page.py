"""Beheer — who has an account, and whether they are getting anywhere.

The operator's window on the thing they host. It exists because the portal is
published now: other people have accounts on it, and the only way to find out
whether anybody was using it was to open psql.

Two states matter more than the rest, and both look like emptiness if you let
them: an account created and never signed in, and an account signed in that
never chose a shop. Those are people who got stuck, as opposed to people who
looked and did not come back, and a dash in a table hides the difference. They
are spelled out here.

The operator check is made in `render_monitor` itself, not only by leaving the
page out of the navigation. A page kept private by nothing linking to it is one
refactor from being public, and this one shows other people's collections.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from bonuschef.portal.accounts import SINGLE_USER, Account
from bonuschef.portal.db import (
    count_flagged_concepts,
    get_engine,
    read_pipeline_health,
    read_account_overview,
    read_account_saved_recipes,
    read_test_environment_state,
)
from bonuschef.portal.freshness import describe_age, now as freshness_now
from bonuschef.portal.review import open_review


def _describe_last_seen(row) -> str:
    """When they were last here, or why there is no answer."""
    if pd.isna(row.get("last_sign_in_at")):
        return "nog nooit aangemeld"
    seen = row.get("last_seen_at")
    if pd.isna(seen):
        return "aangemeld, maar geen sessie meer open"
    return f"laatst geopend {describe_age(seen, freshness_now())}"


def _describe_shop(row) -> str:
    """Which Albert Heijn, by name. A number tells the operator nothing about
    whether somebody picked the right one out of 1,199."""
    if pd.isna(row.get("store_id")):
        return "nog geen winkel gekozen"
    name = row.get("store_name")
    if not name or pd.isna(name):
        return f"winkel {int(row['store_id'])} (niet in de winkellijst)"
    return f"AH {name}"


def render_monitor(account: Account | None = None) -> None:
    account = account or SINGLE_USER

    # The wall, not the decoration. app.py also omits this page for anyone who
    # is not an operator, but that is presentation: it decides what is listed,
    # not what is allowed.
    if not getattr(account, "is_operator", False):
        st.error("Deze pagina is alleen voor de beheerder.")
        return

    st.title("Beheer")

    try:
        engine = get_engine()
        accounts = read_account_overview(engine)
    except Exception as e:
        st.error(f"Geen verbinding met de database: {e}")
        return

    if accounts.empty:
        st.info("Er zijn nog geen accounts.")
        return

    active = int(accounts["last_seen_at"].notna().sum())
    st.caption(
        f"{len(accounts)} account(s), waarvan {active} met een open sessie. "
        f"{int(accounts['saved_count'].sum())} bewaarde recepten in totaal."
    )

    for _, row in accounts.iterrows():
        _render_account(engine, row)

    st.divider()
    _render_pipeline(engine)

    _render_test_environment()


def _render_pipeline(engine) -> None:
    """The machinery behind the answers, and the matcher's outstanding work.

    This used to be on Vanavond, below the recipes, for every account. The portal
    spec says internal diagnostics "MAY remain available, but SHALL NOT occupy
    the primary surfaces" - and a person in a shop can act on none of it, while
    most of it is not theirs to act on at all: a resolution applies to every
    account, so only an operator may set one.

    Moved rather than deleted. Taking it off a shopper's page only works if the
    operator can still see it, and the credential failure deliberately stays
    where the prices are, because it is the one that means they may be wrong.
    """
    st.subheader("De machinerie")

    try:
        health = read_pipeline_health(engine)
    except Exception as e:  # noqa: BLE001 - reported, not swallowed
        st.caption(f"Kon de pijplijn niet lezen: {e}")
        health = pd.DataFrame()

    if health.empty:
        st.caption("Geen gegevens over de jobs.")
    else:
        overdue = health[health["is_overdue"]]
        if overdue.empty:
            st.success("Alle jobs zijn op tijd gelukt.", icon=":material/check:")
        for _, row in overdue.iterrows():
            when = (
                "nog nooit gelukt"
                if pd.isna(row["last_success"])
                else f"{int(row['overdue_h'])} uur geleden voor het laatst gelukt"
            )
            st.warning(
                f"**{row['job_name']}** is {when} — {row['what']} is mogelijk "
                "niet bijgewerkt.",
                icon=":material/sync_problem:",
            )

    try:
        flagged = count_flagged_concepts(engine)
    except Exception:  # noqa: BLE001
        flagged = 0
    if flagged:
        # A flagged concept already has a price; it is just wrong. That reads as
        # nothing being amiss, so it has to be said out loud.
        st.warning(
            f"{flagged} ingrediënt(en) zijn gekoppeld aan een product dat er "
            "waarschijnlijk niet bij hoort. Die recepten hebben nu een prijs "
            "die niet klopt.",
            icon=":material/report:",
        )

    if st.button("Ingrediënten nakijken", icon=":material/link:"):
        open_review(engine, SINGLE_USER)


def _render_test_environment() -> None:
    """Whether there is somewhere to watch a change, and whether it still works.

    This panel exists because the test environment is nobody's production. A
    failed copy or a stopped container sits there unnoticed until somebody
    needs it, which is precisely when a broken one is most expensive - the
    change is ready, the operator wants to see it work, and instead they spend
    the evening fixing the thing that was supposed to give them confidence.

    Omitted entirely when no test environment is configured. A deployment with
    one environment is not broken, and telling it that something is missing is
    how a panel gets ignored.
    """
    # Wrapped even though the reader is written never to raise, matching the
    # pipeline panel above. The reader's promise is a property of its code
    # today; this is a property of the page, and the page's job is to survive
    # anything a diagnostic does.
    try:
        state = read_test_environment_state()
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        st.divider()
        st.subheader("De testomgeving")
        st.caption(f"Kon de testomgeving niet uitlezen: {exc}")
        return
    if state is None:
        return

    st.divider()
    st.subheader("De testomgeving")

    if not state.get("reachable"):
        # Not an error: production is fine, and this is the one part of the
        # page where a fault costs nobody anything until the operator wants to
        # release something.
        st.warning(
            "De testomgeving is niet bereikbaar. Er is nu geen plek om een "
            "wijziging te bekijken voordat anderen die zien.",
            icon=":material/cloud_off:",
        )
        if state.get("error"):
            st.caption(f":gray[{state['error']}]")
        return

    copied = state.get("copied_at")
    if copied is None or pd.isna(copied):
        # Running and empty. A real state, and a different one from
        # unreachable: the stack is up, nobody has copied anything into it.
        st.info(
            "De testomgeving draait, maar er zijn nog geen gegevens naartoe "
            "gekopieerd. Start met `./scripts/copy-to-test.sh`.",
            icon=":material/content_copy:",
        )
        return

    age = describe_age(copied, freshness_now())
    st.success(
        f"De testomgeving draait. Gegevens gekopieerd {age}.", icon=":material/check:"
    )
    if state.get("source"):
        st.caption(f":gray[gekopieerd van {state['source']}]")


def _render_account(engine, row) -> None:
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown(f"### {row['username']}")
            if row.get("is_operator"):
                st.badge("beheerder", color="violet")
            if row.get("must_change_password"):
                st.badge("moet wachtwoord nog wijzigen", color="orange")

        st.markdown(f"**{_describe_shop(row)}**")

        made = row.get("last_made_at")
        bits = [
            _describe_last_seen(row),
            f"account gemaakt {describe_age(row['created_at'], freshness_now())}"
            if pd.notna(row.get("created_at"))
            else "gemaakt op een onbekend moment",
            f"laatst gekookt {describe_age(made, freshness_now())}"
            if pd.notna(made)
            else "nog niets gekookt",
        ]
        st.caption(" · ".join(bits))

        saved = int(row.get("saved_count") or 0)
        if not saved:
            st.caption("Nog geen recepten bewaard.")
            return

        with st.expander(f"Bewaarde recepten ({saved})"):
            _render_saved(engine, int(row["account_id"]))


def _render_saved(engine, account_id: int) -> None:
    recipes = read_account_saved_recipes(engine, account_id)
    if recipes.empty:
        st.caption("Niets gevonden.")
        return
    for _, item in recipes.iterrows():
        name = item.get("recipe_name")
        label = str(name) if name and pd.notna(name) else f"recept {item['recipe_id']}"
        made = item.get("last_made_at")
        when = (
            f"gekookt {describe_age(made, freshness_now())}"
            if pd.notna(made)
            else "nog niet gemaakt"
        )
        saved_at = item.get("saved_at")
        if pd.notna(saved_at):
            when = f"bewaard {describe_age(saved_at, freshness_now())} · {when}"
        st.markdown(f"**{label}**")
        st.caption(when)
