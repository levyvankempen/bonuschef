"""Ingrediënten koppelen — settling what a recipe's ingredients can be bought as.

One dialog over every outstanding ingredient, with the matcher's proposals
already selected. The previous add-recipe flow failed because it cost nine
interactions per ingredient; the cost here is proportional to how many
ingredients are genuinely uncertain, not to how many exist. And because a
resolution belongs to the ingredient rather than to the recipe, settling one
settles it for every recipe that will ever use it.
"""

from __future__ import annotations

import re

import streamlit as st
from dagster import DagsterRunStatus

from bonuschef.portal.db import (
    clear_flag,
    add_resolution_products,
    confirm_resolution,
    read_concept_resolution,
    read_recipe_breakdown_bonus,
    read_recipe_opportunity,
    read_recipe_opportunity_items,
    read_recipe_summary,
    read_unresolved_concepts,
    search_catalogue_products,
)
from bonuschef.portal.matching import candidates
from bonuschef.portal.dagster_client import (
    TERMINAL_STATUSES,
    DagsterTriggerError,
    get_run_status,
)
from bonuschef.portal.rebuild import start_recipe_rebuild
from bonuschef.utils.ah_recipes import fetch_product_taxonomy


def _options(engine, concept_id: int, name: str) -> dict[str, str]:
    """Everything a person could pick: what is attached plus fresh candidates."""
    options: dict[str, str] = {}
    attached = read_concept_resolution(engine, concept_id)
    for _, row in attached.iterrows():
        options[row["product_name"]] = row["product_link"]
    for cand in candidates(engine, name):
        options.setdefault(cand.product_name, cand.product_link)
    return options


def _kinds(options: dict[str, str]) -> dict[str, str]:
    """What kind of thing each candidate is, for showing beside it.

    "AH Witte kaas 40+" and "AH Truffelsalami parmezaanse kaas" read alike in
    a list of names. One is classified as Witte kaas and the other as Salami,
    and that is the distinction a person is being asked to make.

    Best-effort. One batched request covers every candidate in the dialog, and
    if it fails the dialog renders without the annotation rather than not at
    all - a person who opened this is mid-task, and a network error is not a
    reason to take the page away from them.
    """
    ids: dict[int, str] = {}
    for label, link in options.items():
        match = re.match(r"wi(\d+)/", link or "")
        if match:
            ids[int(match.group(1))] = label
    if not ids:
        return {}
    try:
        classified = fetch_product_taxonomy(list(ids))
    except Exception:
        return {}
    out: dict[str, str] = {}
    for webshop_id, hit in classified.items():
        label = ids.get(webshop_id)
        if label and hit.taxonomy_leaf:
            out[label] = hit.taxonomy_leaf
    return out


def _preselected(engine, concept_id: int, options: dict[str, str]) -> list[str]:
    attached = read_concept_resolution(engine, concept_id)
    if attached.empty:
        return []
    links = set(attached["product_link"])
    return [name for name, link in options.items() if link in links]


def _clear_reads() -> None:
    """Drop every cached read a confirmation invalidates.

    The opportunity reads belong here as much as the review ones: correcting an
    ingredient and then seeing the old product for another fifteen minutes reads
    as the correction not having been saved. Missing them is exactly what
    happened - the write landed, the rebuild ran, and the page kept serving its
    cache.
    """
    for reader in (
        read_unresolved_concepts,
        read_concept_resolution,
        search_catalogue_products,
        read_recipe_opportunity,
        read_recipe_opportunity_items,
        read_recipe_summary,
        read_recipe_breakdown_bonus,
    ):
        reader.clear()


# Carries the outcome of a confirmation across the rerun that follows it.
RESOLUTION_RESULT_KEY = "resolution_result"
# And the rebuild it started, so the page can report on it until it finishes.
REBUILD_RUN_KEY = "resolution_rebuild_run"


def render_resolution_result() -> None:
    """What just happened, and what to expect next.

    Called by the page rather than the dialog: st.rerun() closes a dialog, so a
    message rendered inside it is never seen. The counts matter because "niets
    aanvinken" is a legitimate answer that looks identical to having done
    nothing at all.
    """
    result = st.session_state.pop(RESOLUTION_RESULT_KEY, None)
    if not result:
        return
    if result.get("run_id"):
        # Handed to the page so it can report on the rebuild until it finishes,
        # rather than the notice vanishing on the next interaction.
        st.session_state[REBUILD_RUN_KEY] = result["run_id"]
    parts = []
    if result["settled"]:
        parts.append(f"{result['settled']} ingrediënt(en) gekoppeld")
    if result["none_exists"]:
        parts.append(f"{result['none_exists']} vastgelegd als 'geen passend product'")
    st.success(" · ".join(parts) if parts else "Opgeslagen.")
    if not result.get("run_id"):
        st.caption("De prijzen worden bij de volgende berekening bijgewerkt.")


def _render_body(engine, concepts) -> None:
    st.caption(
        "Wat je hier kiest geldt voor élk recept met dit ingrediënt en blijft "
        "bewaard. Meerdere producten mag: we rekenen met de goedkoopste van "
        "vandaag. Zoek gerust een ander product als de suggestie niet klopt."
    )

    chosen: dict[int, list[str]] = {}
    extra: dict[int, list[dict]] = {}

    for _, row in concepts.iterrows():
        concept_id, name = int(row["concept_id"]), row["concept_name"]
        st.markdown(f"**{name}**")
        # Why this one is back. A flagged concept was settled once and has
        # since been found to contradict itself, so arriving here without an
        # explanation would read as the queue having forgotten the decision.
        if row.get("is_flagged"):
            st.warning(
                row.get("flag_reason")
                or "De gekoppelde producten kloppen waarschijnlijk niet.",
                icon=":material/report:",
            )
        options = _options(engine, concept_id, name)

        # Search is always available, not only when nothing was proposed.
        # A wrong proposal is the case that needs it most: "witte kaas 45+"
        # matches only products saying 45+, while the one actually wanted is
        # "witte kaas 40+" - and with the box hidden the only options were to
        # keep the wrong product or leave the ingredient unpriced.
        #
        # Searching is optional either way. Confirming with nothing ticked
        # records "nothing in the catalogue satisfies this", which is an answer.
        term = st.text_input(
            f"Zoek een ander product voor {name}",
            key=f"probe_{concept_id}",
            placeholder=f"bijv. {name.split()[0] if name.split() else name}",
            label_visibility="collapsed",
        )
        if term.strip():
            found = search_catalogue_products(engine, term)
            if found.empty:
                st.caption(f"Geen product gevonden voor '{term.strip()}'.")
            else:
                extra[concept_id] = found.to_dict("records")
                # Merged, not replaced: a search is for adding the right product
                # beside whatever was proposed, and replacing would silently
                # deselect a good proposal the moment someone typed.
                options = {
                    **options,
                    **dict(zip(found["product_name"], found["product_link"])),
                }
        elif not options:
            st.badge("nog geen product gevonden", color="gray")

        kinds = _kinds(options)
        picked = st.multiselect(
            name,
            options=list(options),
            default=_preselected(engine, concept_id, options),
            key=f"pick_{concept_id}",
            label_visibility="collapsed",
            # The retailer's own classification, beside the name. Without it
            # the choice between similarly-named products is a guess.
            format_func=lambda label: (
                f"{label}  ·  {kinds[label]}" if label in kinds else label
            ),
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
            # The person has dealt with it; the flag has served its purpose.
            # Leaving it would put the concept back at the head of the queue
            # they just cleared it from.
            clear_flag(engine, concept_id)
        _clear_reads()
        # Fire-and-forget: blocking here would make settling five ingredients a
        # five-minute wait, since runs are serialised instance-wide. But saying
        # nothing is not part of that bargain - confirming used to rerun into
        # the next batch with no sign anything had happened, which reads as the
        # click not having registered.
        run_id = start_recipe_rebuild()
        settled = sum(1 for links in chosen.values() if links)
        none_exists = len(chosen) - settled
        st.session_state[RESOLUTION_RESULT_KEY] = {
            "settled": settled,
            "none_exists": none_exists,
            "run_id": run_id,
        }
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


def render_rebuild_status() -> None:
    """Report on a recalculation the person started, until it finishes.

    Read from Dagster rather than assumed: "we started a job" is not the same
    claim as "the prices are updated", and the gap between them is where a
    correction looks like it did not save. A queued run says so, because with
    runs serialised instance-wide it may genuinely be waiting behind a scrape.
    """
    run_id = st.session_state.get(REBUILD_RUN_KEY)
    if not run_id:
        return
    try:
        status = get_run_status(run_id)
    except DagsterTriggerError:
        # Losing sight of the run is not worth an error: the write landed, and
        # the next scheduled rebuild picks it up regardless.
        st.session_state.pop(REBUILD_RUN_KEY, None)
        return

    if status in TERMINAL_STATUSES:
        st.session_state.pop(REBUILD_RUN_KEY, None)
        if status == DagsterRunStatus.SUCCESS:
            st.success("De prijzen zijn bijgewerkt met je koppelingen.")
        else:
            st.warning(
                "De prijsberekening is niet afgerond. Je koppelingen zijn wel "
                f"bewaard (run {str(run_id)[:8]}, status {status.value})."
            )
        return

    label = (
        "De prijsberekening staat in de wachtrij…"
        if status == DagsterRunStatus.QUEUED
        else "De prijzen worden herberekend…"
    )
    with st.container(horizontal=True, vertical_alignment="center"):
        st.info(label, icon=":material/hourglass_top:")
        if st.button("Ververs", key="rebuild_poll", icon=":material/refresh:"):
            st.rerun()
