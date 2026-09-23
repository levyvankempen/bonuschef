"""Recepten — the recipes this person saved, as a dashboard.

Replaces a page that rendered the same rows three times: a list, a duplicate
"deze week in de bonus" block over the same recipes, and a detail pane with a
selectbox that made you re-find a recipe you were already looking at.

It answers "show me this recipe". The question people actually bring is "what
shall I cook", and the two differ in what has to be on screen at once: the
cost today, what made it cheap, and when you last had it.

Cards in one column rather than a grid. The app is centred at ~730px because
it is used on a phone in a shop, so two cards side by side is 340px each -
a worse card on a laptop in exchange for nothing on the phone, where it
stacks anyway. Every other page here already uses bordered horizontal
containers, and a grid on one page only makes that page the odd one out.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from bonuschef.portal import offers
from bonuschef.portal.accounts import SINGLE_USER, Account
from bonuschef.portal.db import (
    get_engine,
    read_recipe_opportunity_items,
    mark_recipe_made,
    read_marts_built_at,
    read_recipe_opportunity,
    read_saved_recipes,
    store_for,
    unsave_recipe,
)
from bonuschef.portal.freshness import describe_age, now as freshness_now
from bonuschef.portal.review import open_single

_SORTS = {
    # First, and the default: a collection is usually asked "what have I not
    # had for a while". Alphabetical is the order it had and answers nothing.
    "Langst niet gemaakt": "longest",
    "Voordeligst vandaag": "cheapest",
    "Naam": "name",
}

_FILTER_KEY = "recipes_only_on_offer"
_SORT_KEY = "recipes_sort"
_QUERY_KEY = "recipes_query"


def render_recipes(account: Account | None = None) -> None:
    account = account or SINGLE_USER
    st.title("Recepten")

    engine = get_engine()
    built_at = read_marts_built_at(engine)
    saved = read_saved_recipes(engine, account.account_id, built_at)

    if saved.empty:
        _render_nothing_saved()
        return

    priced = read_recipe_opportunity(engine, store_for(account), built_at)
    # Three states, not one. "Never scraped" is a different statement from
    # "scraped and out of date", and a person who has just chosen a shop needs
    # to hear the first rather than be told their data is stale.
    if offers.snapshot_of(priced) is None:
        st.info(
            "Je winkel is nog niet gescand. De bonus zie je gewoon; laatste "
            "kans-koopjes verschijnen na de eerstvolgende scan."
        )
    else:
        priced, stale_notice = offers.withdraw_stale_clearance(priced)
        if stale_notice:
            st.warning(stale_notice)

    cards = saved.merge(priced, on="recipe_id", how="left")
    on_offer = cards[_is_on_offer(cards)]

    query, sort_key, only_on_offer = _render_controls(len(on_offer))
    shown = on_offer if only_on_offer else cards
    if query:
        shown = shown[shown["recipe_name"].fillna("").str.contains(query, case=False)]

    if shown.empty:
        _render_nothing_matches(cards, only_on_offer, query)
        return

    for _, row in _sorted(shown, sort_key).iterrows():
        _render_card(engine, account, row)


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------


def _render_controls(on_offer_count: int) -> tuple[str, str, bool]:
    """Narrowing, sorting, and the offer filter.

    The count sits in the toggle's label before it is applied, which is what
    stops "nothing on offer" from reading as a broken page: you can see it
    would be empty without making it empty.

    Default off. Turning it on by default hides most of a collection on most
    days, and Vanavond already answers "what is cheap today".
    """
    with st.container(horizontal=True, vertical_alignment="bottom"):
        query = st.text_input("Zoek", key=_QUERY_KEY, placeholder="Naam van een recept")
        # A radio-backed selectbox, not segmented_control: AppTest reads the
        # latter's single-select value as a sequence and iterates the label's
        # characters, which is documented in add_recipe_page.
        label = st.selectbox("Sorteer", options=list(_SORTS), key=_SORT_KEY)
    only = st.toggle(
        f"Alleen wat nu in de aanbieding is ({on_offer_count})", key=_FILTER_KEY
    )
    return query.strip(), _SORTS[label], bool(only)


def _sorted(cards: pd.DataFrame, key: str) -> pd.DataFrame:
    if key == "cheapest":
        return cards.sort_values("cost_today", na_position="last")
    if key == "name":
        return cards.sort_values("recipe_name")
    # Never made first: those are the ones the question is really about.
    made = pd.to_datetime(cards["last_made_at"], utc=True, errors="coerce")
    return cards.assign(_made=made).sort_values("_made", na_position="first")


def _is_on_offer(cards: pd.DataFrame) -> pd.Series:
    discounted = cards.get("items_discounted")
    if discounted is None:
        return pd.Series(False, index=cards.index)
    return discounted.fillna(0) > 0


# ---------------------------------------------------------------------------
# One card
# ---------------------------------------------------------------------------


def _render_card(engine, account: Account, row) -> None:
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center"):
            if isinstance(row.get("image_url"), str) and row["image_url"]:
                st.image(row["image_url"], width=72)
            with st.container():
                st.markdown(f"**{row.get('recipe_name') or 'Naamloos recept'}**")
                _render_price(row)
                _render_badges(row)
                st.caption(_describe_last_made(row.get("last_made_at")))

        _render_ingredients(engine, account, row)

        with st.container(horizontal=True):
            if st.button(
                "Gemaakt vandaag",
                key=f"made_{row['recipe_id']}",
                icon=":material/check:",
            ):
                mark_recipe_made(engine, account.account_id, int(row["recipe_id"]))
                st.rerun()
            if st.button(
                "Verwijderen",
                key=f"drop_{row['recipe_id']}",
                icon=":material/delete:",
            ):
                unsave_recipe(engine, account.account_id, int(row["recipe_id"]))
                st.rerun()


_OPEN_KEY = "recipes_open_card"


def _render_ingredients(engine, account: Account, row) -> None:
    """The lines behind a card, and the way to correct one.

    Fetched only for the card that is open. An expander renders its contents
    whether or not it is expanded, so a hundred saved recipes would each pull
    their ingredient rows on every rerun - and the existing portal requirement
    forbids retrieving unbounded result sets to display a bounded view.

    The correction has to be here. The page this replaced satisfied "a wrong
    match is correctable where it is visible" through its detail pane, and
    deleting that pane without carrying the correction across would have
    quietly regressed a live requirement.
    """
    recipe_id = int(row["recipe_id"])
    total = row.get("items_total")
    label = "Ingrediënten" if pd.isna(total) else f"Ingrediënten ({int(total)})"
    is_open = st.session_state.get(_OPEN_KEY) == recipe_id

    if st.button(
        label,
        key=f"open_{recipe_id}",
        icon=":material/expand_less:" if is_open else ":material/expand_more:",
    ):
        st.session_state[_OPEN_KEY] = None if is_open else recipe_id
        st.rerun()

    if not is_open:
        return

    items = read_recipe_opportunity_items(
        engine, recipe_id, store_for(account), read_marts_built_at(engine)
    )
    if items.empty:
        st.caption("Voor dit recept zijn geen ingrediënten bekend.")
        return

    for _, item in items.iterrows():
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown(str(item.get("item_label") or "?"))
            if pd.isna(item.get("price_today")):
                st.caption("nog niet gekoppeld")
            if pd.notna(item.get("concept_id")):
                # Keyed on recipe AND line: item_key is "c:<concept_id>", so
                # two recipes both containing onions would otherwise collide.
                if st.button(
                    "Klopt niet",
                    key=f"fix_{recipe_id}_{item['item_key']}",
                    icon=":material/edit:",
                    help="Kies zelf het juiste product voor dit ingrediënt",
                ):
                    open_single(
                        engine, int(item["concept_id"]), str(item["item_label"])
                    )


def _render_price(row) -> None:
    """Exact when every ingredient is priced, an estimate when not.

    The "±" and the coverage together are the honest form: a total over five
    of eight ingredients is not the price of the dish, and printing it bare
    invites somebody to trust it.
    """
    cost = row.get("cost_today")
    if pd.notna(cost):
        ordinary = row.get("cost_ordinary")
        was = (
            f" · ~~{offers.euro(ordinary)}~~"
            if pd.notna(ordinary) and ordinary > cost
            else ""
        )
        st.markdown(f"{offers.euro(cost)}{was}")
        return

    partial = row.get("partial_cost_today")
    priced, total = row.get("items_priced"), row.get("items_total")
    if pd.notna(partial) and pd.notna(priced) and pd.notna(total):
        st.markdown(f"±{offers.euro(partial)}")
        st.caption(f"Schatting over {int(priced)} van {int(total)} ingrediënten")
        return
    st.caption("Van geen enkel ingrediënt is de prijs bekend.")


def _render_badges(row) -> None:
    clearance = row.get("items_discounted_clearance") or 0
    discounted = row.get("items_discounted") or 0
    bonus = max(int(discounted) - int(clearance), 0)
    with st.container(horizontal=True):
        if bonus:
            st.badge(f"{bonus}× bonus", color="green", icon=":material/savings:")
        if int(clearance):
            st.badge(
                f"{int(clearance)}× laatste kans",
                color="orange",
                icon=":material/schedule:",
            )
        unresolved = row.get("items_unresolved") or 0
        if int(unresolved):
            st.badge(
                f"{int(unresolved)} nog niet gekoppeld",
                color="grey",
                icon=":material/help:",
            )


def _describe_last_made(value) -> str:
    """ "Nog niet gemaakt" is a different statement from a zero date."""
    stamp = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(stamp):
        return "Nog niet gemaakt"
    return f"Vorige keer {describe_age(stamp, freshness_now())}"


# ---------------------------------------------------------------------------
# Nothing to show
# ---------------------------------------------------------------------------


def _render_nothing_saved() -> None:
    """A dead end is the failure here. The page says where recipes come from
    and links to both, rather than reporting an absence."""
    st.info("Je hebt nog geen recepten bewaard.")
    st.markdown(
        "Op **Vanavond** staat wat vandaag het voordeligst is — bewaar daar "
        "wat je wilt maken. Of zoek er zelf een op **Toevoegen**."
    )
    with st.container(horizontal=True):
        st.page_link("vanavond", label="Vanavond", icon=":material/local_dining:")
        st.page_link("toevoegen", label="Toevoegen", icon=":material/add:")


def _render_nothing_matches(
    cards: pd.DataFrame, only_on_offer: bool, query: str
) -> None:
    """Still answer the question that was asked.

    An empty grid under a filter reads as a failure. Saying what is not there
    and then answering the next question is what the clearance page does when
    the day's scan finds nothing.
    """
    if query:
        st.info(f"Geen bewaard recept met '{query}' in de naam.")
        return
    if only_on_offer:
        st.info(
            "Van je bewaarde recepten staat er vandaag niets in de aanbieding. "
            "Dat is een antwoord, geen storing."
        )
        longest = _sorted(cards, "longest").head(1)
        if not longest.empty:
            name = longest.iloc[0].get("recipe_name")
            st.markdown(f"**Wel het langst niet gemaakt:** {name}")
        return
    st.info("Geen recepten om te tonen.")
