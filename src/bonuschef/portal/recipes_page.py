"""Recipes page — recipe overview, cost history, and ingredient breakdown."""

import streamlit as st

from bonuschef.portal.db import (
    get_engine,
    read_recipe_bonus_summary,
    read_recipe_breakdown_bonus,
    read_recipe_cost_history,
    read_recipe_summary,
)
from bonuschef.portal.ui import display_cost_breakdown, display_total_cost_line


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
        use_container_width=True,
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


def _render_cost_history(engine):
    """Display multi-recipe cost history line chart."""
    history_df = read_recipe_cost_history(engine)

    if history_df.empty:
        return

    st.subheader("Recipe Cost History")
    display_total_cost_line(
        history_df,
        date_col="snapshot_timestamp",
        value_col="total_cost_observed",
        recipe_col="recipe_name",
    )


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

    display_cost_breakdown(breakdown_df)

    st.markdown("**Ingredients**")
    for _, row in breakdown_df.iterrows():
        col_img, col_name, col_price, col_qty, col_cost, col_bonus = st.columns(
            [1, 3, 1, 1, 1, 2]
        )

        with col_img:
            if row.get("image_url"):
                st.image(row["image_url"], width=80)

        with col_name:
            if row.get("product_url"):
                st.markdown(f"[{row['product_name']}]({row['product_url']})")
            else:
                st.write(row["product_name"])

        with col_price:
            st.write(f"\u20ac{row['price']:.2f}")

        with col_qty:
            st.write(f"x{row['quantity']}")

        with col_cost:
            st.write(f"\u20ac{row['item_cost']:.2f}")

        with col_bonus:
            if row.get("is_on_bonus"):
                mechanism = row.get("bonus_mechanism") or "BONUS"
                bonus_price = row.get("bonus_price")
                tracked_price = row.get("price")
                ah_price = row.get("price_before_bonus")

                st.markdown(f":green[**BONUS**] {mechanism}")

                # Show all three prices for comparison
                if bonus_price is not None:
                    price_parts = [f"\u20ac{bonus_price:.2f} bonus"]
                    if tracked_price is not None:
                        price_parts.append(f"\u20ac{tracked_price:.2f} tracked")
                    if ah_price is not None and ah_price != tracked_price:
                        # Flag inflated AH price in orange
                        if tracked_price is not None and ah_price > tracked_price:
                            price_parts.append(
                                f":orange[\u20ac{ah_price:.2f} AH]"
                            )
                        else:
                            price_parts.append(f"\u20ac{ah_price:.2f} AH")
                    st.caption(" | ".join(price_parts))


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
    _render_cost_history(engine)
    _render_recipe_detail(engine, summary_df)
