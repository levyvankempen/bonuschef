"""Toevoegen — een recept overnemen uit de Albert Heijn-catalogus.

The old flow took roughly nine interactions per ingredient and ended by asking
the user to run `dbt run` in a terminal, which is why exactly two recipes exist.
This one is a search, a look, and a button.
"""

from __future__ import annotations

import streamlit as st

from bonuschef.portal.db import (
    ensure_catalogue_tables,
    get_engine,
    is_adopted,
    propose_products,
    save_adopted_recipe,
)
from bonuschef.portal.manual_recipe import render_manual_entry
from bonuschef.portal.matching import propose_for
from bonuschef.portal.rebuild import start_recipe_rebuild
from bonuschef.portal.review import open_review
from bonuschef.utils.ah_recipes import (
    AHRecipeNotFound,
    facet_values,
    AHRecipeShapeError,
    AHRecipeUnavailable,
    fetch_recipe,
    search_recipes,
)

_QUERY = "cat_query"
_PICKED = "cat_picked"
_ADDED = "cat_added"


@st.cache_resource
def _ensure(_engine) -> bool:
    ensure_catalogue_tables(_engine)
    return True


_SORT_LABELS = {
    "Nieuw": "NEWEST",
    "Populair": "POPULAR",
    "In trek": "TRENDING",
}


@st.cache_data(ttl=900, show_spinner=False)
def _search(query: str):
    return search_recipes(query, size=8)


@st.cache_data(ttl=900, show_spinner=False)
def _browse(sort_by: str, season: str | None):
    """Allerhande without a search term, which is how people actually browse."""
    filters: list[dict[str, object]] | None = (
        [{"group": "seizoen", "values": [season]}] if season else None
    )
    return search_recipes(size=8, sort_by=sort_by, filters=filters)


@st.cache_data(ttl=3600, show_spinner=False)
def _seasons() -> list[str]:
    """Read from the catalogue: a hardcoded copy rots the day AH renames one."""
    try:
        return facet_values("seizoen")
    except (AHRecipeUnavailable, AHRecipeShapeError):
        return []


def _render_search() -> None:
    """A form, deliberately.

    A bare text_input reruns the script on every keystroke, and every rerun
    would be a fresh call to an unofficial third-party API to render a list
    nobody has asked for yet — the same mistake as fetching a product image per
    row, which the portal capability forbids.
    """
    with st.form("catalogue_search", border=False):
        field, go = st.columns([4, 1], vertical_alignment="bottom")
        with field:
            query = st.text_input(
                "Zoek een recept",
                placeholder="zuurkoolstamppot",
                label_visibility="collapsed",
            )
        with go:
            submitted = st.form_submit_button("Zoek", type="primary", width="stretch")
    if submitted and query.strip():
        st.session_state[_QUERY] = query.strip()
        st.session_state.pop(_PICKED, None)
        st.session_state.pop(_ADDED, None)


def _render_hits(hits) -> None:
    for hit in hits:
        with st.container(border=True, horizontal=True, vertical_alignment="center"):
            if hit.image_url:
                st.image(hit.image_url, width=72)
            with st.container():
                st.markdown(f"**{hit.title}**")
            with st.container(horizontal_alignment="right"):
                if st.button("Bekijken", key=f"pick_{hit.recipe_id}"):
                    st.session_state[_PICKED] = hit.recipe_id
                    st.rerun()


def _render_browse() -> None:
    """Allerhande, before anything has been typed.

    The page used to open on an empty search box, which required knowing a dish
    name before the catalogue was any use at all.
    """
    st.markdown("**Uit de Allerhande**")
    controls = st.columns([2, 2])
    with controls[0]:
        # radio, not segmented_control: AppTest reads the latter's single-select
        # value as a sequence and iterates the label's characters.
        label = st.radio(
            "Sorteren",
            list(_SORT_LABELS),
            horizontal=True,
            label_visibility="collapsed",
        )
    seasons = _seasons()
    season = None
    with controls[1]:
        if seasons:
            season = st.selectbox(
                "Seizoen",
                ["Alle seizoenen", *seasons],
                label_visibility="collapsed",
            )
            season = None if season == "Alle seizoenen" else season

    try:
        with st.spinner("Recepten ophalen…"):
            page = _browse(_SORT_LABELS.get(label or "Nieuw", "NEWEST"), season)
    except AHRecipeUnavailable as exc:
        # Distinct from an empty catalogue, which would read as "there are no
        # recipes" rather than "we could not ask".
        st.error(
            "De receptencatalogus van Albert Heijn is nu niet bereikbaar. "
            "Je eigen recepten blijven gewoon werken."
        )
        st.caption(str(exc))
        return
    except AHRecipeShapeError as exc:
        st.error("Albert Heijn gaf een antwoord dat we niet konden lezen.")
        st.caption(str(exc))
        return

    if not page.hits:
        st.info("Geen recepten gevonden voor deze keuze.")
        return
    st.caption(f"{page.total} recepten")
    _render_hits(page.hits)


def _render_results(query: str) -> None:
    try:
        with st.spinner(f"Zoeken naar “{query}” bij Albert Heijn…"):
            page = _search(query)
    except AHRecipeUnavailable as exc:
        # Distinct from "niets gevonden". That distinction is the whole reason
        # the client carries a canary.
        st.error(
            "De receptencatalogus van Albert Heijn is nu niet bereikbaar. "
            "Je eigen recepten blijven gewoon werken."
        )
        st.caption(str(exc))
        return
    except AHRecipeShapeError as exc:
        st.error(
            "Albert Heijn gaf een antwoord dat we niet konden lezen — "
            "waarschijnlijk is hun API veranderd. Er is niets toegevoegd."
        )
        st.caption(str(exc))
        return

    if not page.hits:
        st.info(f"Geen recepten gevonden voor “{query}”. Probeer een ander woord.")
        return

    st.caption(f"{page.total} recepten gevonden")
    # Picking IS selecting: the old flow showed a table and then made you find
    # the same name again in a separate control.
    _render_hits(page.hits)


def _adopt(engine, recipe) -> None:
    save_adopted_recipe(engine, recipe)
    concepts = {i.concept_id: i.name for i in recipe.ingredients}
    proposals = propose_for(engine, concepts)
    propose_products(engine, proposals)
    start_recipe_rebuild()
    matched = {p["concept_id"] for p in proposals}
    st.session_state[_ADDED] = {
        "title": recipe.title,
        "servings": recipe.servings,
        "n_ingredients": len(recipe.ingredients),
        "n_unmatched": len(concepts) - len(matched),
    }
    st.session_state.pop(_PICKED, None)


def _render_preview(engine, ah_id: int) -> None:
    if st.button("← Terug naar de resultaten", type="tertiary"):
        st.session_state.pop(_PICKED, None)
        st.rerun()

    try:
        with st.spinner("Recept ophalen…"):
            recipe = fetch_recipe(ah_id)
    except AHRecipeNotFound:
        st.warning("Albert Heijn heeft dit recept niet meer.")
        return
    except AHRecipeUnavailable as exc:
        st.error("Albert Heijn is nu niet bereikbaar. Probeer het zo nog eens.")
        st.caption(str(exc))
        return
    except AHRecipeShapeError as exc:
        st.error(
            "Dit recept kunnen we niet lezen — de ingrediënten ontbreken of "
            "hebben een vorm die we niet kennen. Er is niets toegevoegd."
        )
        st.caption(str(exc))
        return

    st.subheader(recipe.title)
    st.caption(f"{recipe.servings} personen · {len(recipe.ingredients)} ingrediënten")
    for ing in recipe.ingredients:
        with st.container(border=True, horizontal=True, vertical_alignment="center"):
            st.markdown(f"**{ing.name}**")
            with st.container(horizontal_alignment="right"):
                unit = f" {ing.unit}" if ing.unit else ""
                st.caption(f"{ing.quantity:g}{unit}")

    if is_adopted(engine, ah_id):
        st.info(f"“{recipe.title}” staat al bij je recepten.")
        return

    if st.button("Voeg toe aan mijn recepten", type="primary", width="stretch"):
        _adopt(engine, recipe)
        st.rerun()


def _engine_for_review():
    return get_engine()


def _render_added(added: dict) -> None:
    with st.container(border=True):
        st.markdown(f"### {added['title']}")
        st.caption(
            f"{added['n_ingredients']} ingrediënten · {added['servings']} personen"
        )
        if added["n_unmatched"]:
            st.badge(
                f"{added['n_unmatched']} zonder product",
                color="orange",
                icon=":material/help:",
            )
            st.caption(
                "Die tellen nog niet mee in de prijs. Koppel ze één keer en elk "
                "recept met dat ingrediënt is meteen compleet."
            )
            if st.button("Nakijken", width="stretch"):
                open_review(_engine_for_review())
        else:
            st.badge(
                "alle ingrediënten herkend",
                color="green",
                icon=":material/check_circle:",
            )
        st.caption("De prijs wordt op de achtergrond berekend.")
    st.divider()
    st.markdown("**Nog een recept toevoegen**")


def render_add_recipe() -> None:
    st.title("Recept toevoegen")
    st.caption(
        "Zoek een recept bij Albert Heijn en neem het in één keer over. "
        "We rekenen met één product per ingrediënt."
    )

    try:
        engine = get_engine()
        _ensure(engine)
    except Exception as exc:
        st.error(f"Geen verbinding met de database: {exc}")
        return

    if (added := st.session_state.get(_ADDED)) is not None:
        _render_added(added)
        _render_search()
    elif (picked := st.session_state.get(_PICKED)) is not None:
        _render_preview(engine, picked)
    else:
        _render_search()
        if query := st.session_state.get(_QUERY):
            _render_results(query)
        else:
            _render_browse()

    with st.expander("Zelf een recept invoeren"):
        render_manual_entry()
