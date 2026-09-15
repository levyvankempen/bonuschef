"""Ingrediënten koppelen — settling what a recipe's ingredients can be bought as.

One dialog over every outstanding ingredient, with the matcher's proposals
already selected. The previous add-recipe flow failed because it cost nine
interactions per ingredient; the cost here is proportional to how many
ingredients are genuinely uncertain, not to how many exist. And because a
resolution belongs to the ingredient rather than to the recipe, settling one
settles it for every recipe that will ever use it.
"""

from __future__ import annotations

import streamlit as st

from bonuschef.portal.db import (
    add_resolution_products,
    confirm_resolution,
    read_concept_resolution,
    read_unresolved_concepts,
    search_catalogue_products,
)
from bonuschef.portal.matching import candidates
from bonuschef.portal.rebuild import start_recipe_rebuild


def _options(engine, concept_id: int, name: str) -> dict[str, str]:
    """Everything a person could pick: what is attached plus fresh candidates."""
    options: dict[str, str] = {}
    attached = read_concept_resolution(engine, concept_id)
    for _, row in attached.iterrows():
        options[row["product_name"]] = row["product_link"]
    for cand in candidates(engine, name):
        options.setdefault(cand.product_name, cand.product_link)
    return options


def _preselected(engine, concept_id: int, options: dict[str, str]) -> list[str]:
    attached = read_concept_resolution(engine, concept_id)
    if attached.empty:
        return []
    links = set(attached["product_link"])
    return [name for name, link in options.items() if link in links]


def _clear_reads() -> None:
    for reader in (
        read_unresolved_concepts,
        read_concept_resolution,
        search_catalogue_products,
    ):
        reader.clear()


def _render_body(engine, concepts) -> None:
    st.caption(
        "Wat je hier kiest geldt voor élk recept met dit ingrediënt. "
        "Meerdere producten mag: we rekenen met de goedkoopste van vandaag."
    )

    chosen: dict[int, list[str]] = {}
    extra: dict[int, list[dict]] = {}

    for _, row in concepts.iterrows():
        concept_id, name = int(row["concept_id"]), row["concept_name"]
        st.markdown(f"**{name}**")
        options = _options(engine, concept_id, name)

        if not options:
            # The only place in the whole flow where typing happens, and it is
            # optional: leaving it empty records "nothing satisfies this".
            term = st.text_input(
                f"Zoek een product voor {name}",
                key=f"probe_{concept_id}",
                placeholder=name,
                label_visibility="collapsed",
            )
            if term.strip():
                found = search_catalogue_products(engine, term)
                options = dict(zip(found["product_name"], found["product_link"]))
                extra[concept_id] = found.to_dict("records")
            else:
                st.badge("nog geen product gevonden", color="gray")

        picked = st.multiselect(
            name,
            options=list(options),
            default=_preselected(engine, concept_id, options),
            key=f"pick_{concept_id}",
            label_visibility="collapsed",
        )
        chosen[concept_id] = [options[p] for p in picked]
        st.divider()

    st.caption(
        "Niets aanvinken mag ook — het ingrediënt blijft zichtbaar in het "
        "recept, maar telt niet mee in de prijs."
    )
    if st.button("Bevestigen", type="primary", width="stretch"):
        for concept_id, links in chosen.items():
            picked_links = set(links)
            new_products = [
                {"product_link": r["product_link"], "product_name": r["product_name"]}
                for r in extra.get(concept_id, [])
                if r["product_link"] in picked_links
            ]
            add_resolution_products(engine, concept_id, new_products)
            confirm_resolution(engine, concept_id, links)
        _clear_reads()
        # Fire-and-forget: blocking here would make settling five ingredients a
        # five-minute wait, since runs are serialised instance-wide.
        start_recipe_rebuild()
        st.rerun()


# A sitting's worth. The pool contributes over a thousand outstanding
# ingredients, and a dialog that renders them all is not a queue but a wall.
# They are ordered most-used first, which is what makes a bounded slice the
# useful one: the top of the list is where a few minutes buys the most.
REVIEW_BATCH = 20


@st.dialog("Ingrediënten koppelen", width="large")
def open_review(engine, *, recipe_id: int | None = None) -> None:
    """The most-used outstanding ingredients, settled by one button."""
    concepts = read_unresolved_concepts(engine, recipe_id=recipe_id, limit=REVIEW_BATCH)
    if concepts.empty:
        st.success("Alles is al gekoppeld.")
        return
    if "uses" in concepts:
        st.caption("De meest gebruikte ingrediënten eerst — deze wegen het zwaarst.")
    _render_body(engine, concepts)


@st.dialog("Ingrediënt koppelen", width="large")
def open_single(engine, concept_id: int, concept_name: str) -> None:
    """The same thing scoped to one ingredient, for correcting a wrong match."""
    import pandas as pd

    _render_body(
        engine,
        pd.DataFrame([{"concept_id": concept_id, "concept_name": concept_name}]),
    )
