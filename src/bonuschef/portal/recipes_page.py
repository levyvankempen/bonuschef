"""Recipes page — recipe overview, cost history, and ingredient breakdown."""

import streamlit as st

from bonuschef.portal.db import (
    get_engine,
    read_recipe_breakdown,
    read_recipe_cost_history,
    read_recipe_summary,
)
from bonuschef.portal.ui import display_cost_breakdown, display_total_cost_line


def _render_recipe_summary(summary_df):
    """Display recipe overview table."""
    st.subheader("Recipe Overview")

    display_df = summary_df[["recipe_name", "servings", "total_cost", "cost_per_serving"]].copy()
    display_df = display_df.rename(columns={
        "recipe_name": "Recipe",
        "servings": "Servings",
        "total_cost": "Total Cost (€)",
        "cost_per_serving": "Per Serving (€)",
    })

    st.dataframe(
        display_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Total Cost (€)": st.column_config.NumberColumn(format="€%.2f"),
            "Per Serving (€)": st.column_config.NumberColumn(format="€%.2f"),
        },
    )


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
    breakdown_df = read_recipe_breakdown(engine, recipe_id)

    if breakdown_df.empty:
        st.warning("No ingredient data available for this recipe.")
        return

    display_cost_breakdown(breakdown_df)

    st.markdown("**Ingredients**")
    for _, row in breakdown_df.iterrows():
        col_img, col_name, col_price, col_qty, col_cost = st.columns([1, 4, 1, 1, 1])

        with col_img:
            if row.get("image_url"):
                st.image(row["image_url"], width=80)

        with col_name:
            if row.get("product_url"):
                st.markdown(f"[{row['product_name']}]({row['product_url']})")
            else:
                st.write(row["product_name"])

        with col_price:
            st.write(f"€{row['price']:.2f}")

        with col_qty:
            st.write(f"x{row['quantity']}")

        with col_cost:
            st.write(f"€{row['item_cost']:.2f}")


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
    _render_cost_history(engine)
    _render_recipe_detail(engine, summary_df)
