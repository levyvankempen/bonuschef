"""Recipes page — recipe overview, cost history, and ingredient breakdown."""

import streamlit as st

from bonuschef.portal.db import (
    get_engine,
    read_recipe_bonus_summary,
    read_recipe_breakdown_bonus,
    read_recipe_summary,
)


def _render_recipe_summary(summary_df):
    """Display recipe overview table."""
    st.subheader("Recipe Overview")

    display_df = summary_df[
        ["recipe_name", "servings", "total_cost", "cost_per_serving"]
    ].copy()
    display_df = display_df.rename(
        columns={
            "recipe_name": "Recipe",
            "servings": "Servings",
            "total_cost": "Total Cost (\u20ac)",
            "cost_per_serving": "Per Serving (\u20ac)",
        }
    )

    st.dataframe(
        display_df,
        hide_index=True,
        column_config={
            "Total Cost (\u20ac)": st.column_config.NumberColumn(format="\u20ac%.2f"),
            "Per Serving (\u20ac)": st.column_config.NumberColumn(format="\u20ac%.2f"),
        },
    )


def _render_bonus_highlights(engine):
    """Show which recipes have ingredients currently on bonus."""
    bonus_df = read_recipe_bonus_summary(engine)
    if bonus_df.empty or bonus_df["bonus_count"].sum() == 0:
        return

    st.subheader("Current Bonus Deals")
    has_bonus = bonus_df[bonus_df["bonus_count"] > 0].copy()
    if has_bonus.empty:
        return

    for _, row in has_bonus.iterrows():
        real = row["total_real_savings"]
        advertised = row["total_advertised_savings"]

        parts = [
            f"**{row['recipe_name']}**: "
            f"{row['bonus_count']}/{row['total_ingredients']} ingredients on bonus"
        ]
        if real > 0:
            parts.append(f" \u2014 save **\u20ac{real:.2f}**")
        if advertised > 0 and advertised != real:
            parts.append(f" (AH claims \u20ac{advertised:.2f})")

        st.markdown("".join(parts))


def _render_recipe_detail(engine, summary_df):
    """Drill-down into a specific recipe's ingredients."""
    st.subheader("Recipe Details")

    recipe_options = dict(zip(summary_df["recipe_name"], summary_df["recipe_id"]))
    selected_name = st.selectbox("Select a recipe", options=list(recipe_options.keys()))

    if not selected_name:
        return

    recipe_id = recipe_options[selected_name]
    breakdown_df = read_recipe_breakdown_bonus(engine, recipe_id)

    if breakdown_df.empty:
        st.warning("No ingredient data available for this recipe.")
        return

    real_total = breakdown_df["real_savings"].sum()
    adv_total = breakdown_df["advertised_savings"].sum()
    if real_total > 0:
        msg = f"Ingredients on bonus! Real savings: \u20ac{real_total:.2f}"
        if adv_total > 0 and adv_total != real_total:
            msg += f" (AH advertises \u20ac{adv_total:.2f})"
        st.success(msg)

    st.markdown("**Ingrediënten**")
    for _, row in breakdown_df.iterrows():
        # One card per ingredient. Six st.columns per row gave each cell about
        # 40px on a phone, and st.columns does not wrap.
        with st.container(border=True, horizontal=True, vertical_alignment="center"):
            if row.get("image_url"):
                st.image(row["image_url"], width=56)
            with st.container():
                if row.get("product_url"):
                    st.markdown(f"**[{row['product_name']}]({row['product_url']})**")
                else:
                    st.markdown(f"**{row['product_name']}**")
                st.caption(f"{row['quantity']}× · €{row['price']:.2f} per stuk")
            with st.container(horizontal_alignment="right"):
                st.markdown(f"**€{row['item_cost']:.2f}**")
                if row.get("is_on_bonus"):
                    st.badge(
                        row.get("bonus_mechanism") or "Bonus",
                        color="green",
                        icon=":material/savings:",
                    )
                    # The honest-price insight, in one line rather than three
                    # prices separated by pipes. This is the project's thesis and
                    # it belongs where the saving is, not in a separate table.
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


def render_recipes():
    st.title("Recipes")

    try:
        engine = get_engine()
    except Exception as e:
        st.error(f"Database connection error: {e}")
        return

    summary_df = read_recipe_summary(engine)

    if summary_df.empty:
        st.info("No recipes found. Add a recipe first.")
        return

    _render_recipe_summary(summary_df)
    _render_bonus_highlights(engine)
    _render_recipe_detail(engine, summary_df)
