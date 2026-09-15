"""Recipes page — recipe overview, cost history, and ingredient breakdown."""

import pandas as pd
import streamlit as st

from bonuschef.portal.review import (
    open_single,
    render_rebuild_status,
    render_resolution_result,
)
from bonuschef.portal.db import (
    get_engine,
    read_recipe_bonus_summary,
    read_recipe_breakdown_bonus,
    read_recipe_summary,
)


def _render_recipe_summary(summary_df):
    """One card per recipe.

    A recipe whose ingredients are not all priced shows what is known with a
    trailing "+", never a total. Silently publishing the sum of a partial
    basket is how a recipe missing its rookworst wins a "cheapest tonight"
    comparison against a complete one.
    """
    st.subheader("Mijn recepten")
    for _, row in summary_df.iterrows():
        with st.container(border=True, horizontal=True, vertical_alignment="center"):
            with st.container():
                st.markdown(f"**{row['recipe_name']}**")
                st.caption(f"{int(row['servings'])} personen")
                unresolved = int(row.get("items_unresolved") or 0)
                unpriced = int(row.get("items_total") or 0) - int(
                    row.get("items_priced") or 0
                )
                if unpriced:
                    st.badge(
                        f"{unpriced} van {int(row['items_total'])} zonder prijs",
                        color="orange",
                        icon=":material/help:",
                    )
                    if unresolved:
                        st.caption(
                            f"{unresolved} ingrediënt(en) zijn nog niet aan een "
                            "product gekoppeld."
                        )
            with st.container(horizontal_alignment="right"):
                if pd.notna(row["total_cost"]):
                    st.markdown(f"**€{row['total_cost']:.2f}**")
                    st.caption(f"€{row['cost_per_serving']:.2f} p.p.")
                elif pd.notna(row.get("partial_cost_observed")):
                    # The "+" is the whole honesty mechanism, in one character.
                    st.markdown(f"**€{row['partial_cost_observed']:.2f}+**")
                    st.caption("nog niet compleet")
                else:
                    st.caption("nog geen prijs")


def _render_bonus_highlights(engine):
    """Show which recipes have ingredients currently on bonus."""
    bonus_df = read_recipe_bonus_summary(engine)
    if bonus_df.empty or bonus_df["bonus_count"].sum() == 0:
        return

    st.subheader("Deze week in de bonus")
    has_bonus = bonus_df[bonus_df["bonus_count"] > 0].copy()
    if has_bonus.empty:
        return

    for _, row in has_bonus.iterrows():
        real = row["total_real_savings"]
        advertised = row["total_advertised_savings"]

        parts = [
            f"**{row['recipe_name']}**: "
            f"{row['bonus_count']}/{row['total_ingredients']} "
            "ingrediënten in de bonus"
        ]
        if real > 0:
            parts.append(f" — je bespaart **€{real:.2f}**")
        if advertised > 0 and advertised != real:
            parts.append(f" (AH adverteert €{advertised:.2f})")

        st.markdown("".join(parts))


def _render_recipe_detail(engine, summary_df):
    """Drill-down into a specific recipe's ingredients."""
    st.subheader("Recept")

    recipe_options = dict(zip(summary_df["recipe_name"], summary_df["recipe_id"]))
    selected_name = st.selectbox("Kies een recept", options=list(recipe_options.keys()))

    if not selected_name:
        return

    recipe_id = recipe_options[selected_name]
    breakdown_df = read_recipe_breakdown_bonus(engine, recipe_id)

    if breakdown_df.empty:
        st.warning("Voor dit recept zijn geen ingrediënten bekend.")
        return

    real_total = breakdown_df["real_savings"].sum()
    adv_total = breakdown_df["advertised_savings"].sum()
    if real_total > 0:
        msg = f"Ingrediënten in de bonus — je bespaart €{real_total:.2f}"
        if adv_total > 0 and adv_total != real_total:
            msg += f" (AH adverteert €{adv_total:.2f})"
        st.success(msg)

    st.markdown("**Ingrediënten**")
    for _, row in breakdown_df.iterrows():
        # One card per ingredient, in one of three states: resolved to a
        # product, unresolved, or decided to have no purchasable equivalent.
        # The third is a decision and must not read like an oversight.
        unresolved = bool(row.get("is_unresolved"))
        no_product = row.get("review_state") == "none_exists"
        label = row.get("item_label") or row.get("product_name")
        with st.container(border=True, horizontal=True, vertical_alignment="center"):
            if row.get("image_url") and not unresolved:
                st.image(row["image_url"], width=56)
            with st.container():
                if unresolved:
                    st.markdown(f"**{label}**")
                    if no_product:
                        st.badge(
                            "geen product",
                            color="gray",
                            icon=":material/block:",
                        )
                        st.caption("Hiervoor is bewust geen product gekozen.")
                    else:
                        st.badge(
                            "nog niet gekoppeld",
                            color="orange",
                            icon=":material/help:",
                        )
                elif row.get("product_url"):
                    st.markdown(f"**[{row['product_name']}]({row['product_url']})**")
                    st.caption(f"{row['quantity']}× · €{row['price']:.2f} per stuk")
                else:
                    st.markdown(f"**{row['product_name']}**")
                    st.caption(f"{row['quantity']}× · €{row['price']:.2f} per stuk")
            with st.container(horizontal_alignment="right"):
                if not unresolved and pd.notna(row.get("item_cost")):
                    st.markdown(f"**€{row['item_cost']:.2f}**")
                if row.get("is_on_bonus"):
                    st.badge(
                        row.get("bonus_mechanism") or "Bonus",
                        color="green",
                        icon=":material/savings:",
                    )
                    # The honest-price insight, in one line rather than three
                    # prices separated by pipes. This is the project's thesis
                    # and it belongs where the saving is.
                    ah_price = row.get("price_before_bonus")
                    tracked = row.get("price")
                    if (
                        ah_price is not None
                        and tracked is not None
                        and ah_price > tracked
                    ):
                        st.caption(
                            f"AH rekent €{ah_price:.2f} als 'van'-prijs; "
                            f"wij zagen €{tracked:.2f}."
                        )
                # Correctable where the gap is visible: noticing and fixing are
                # one act, and because resolution lives on the ingredient, this
                # corrects every recipe using it.
                if pd.notna(row.get("concept_id")):
                    if st.button(
                        "wijzig",
                        key=f"fix_{row['recipe_id']}_{row['item_key']}",
                        type="tertiary",
                    ):
                        open_single(get_engine(), int(row["concept_id"]), str(label))


def render_recipes():
    st.title("Recepten")

    # The same dialog runs from here, so the same feedback belongs here.
    render_resolution_result()
    render_rebuild_status()

    try:
        engine = get_engine()
    except Exception as e:
        st.error(f"Geen verbinding met de database: {e}")
        return

    summary_df = read_recipe_summary(engine)

    if summary_df.empty:
        st.info("Nog geen recepten. Voeg er eerst een toe.")
        return

    _render_recipe_summary(summary_df)
    _render_bonus_highlights(engine)
    _render_recipe_detail(engine, summary_df)
