"""Streamlit UI helper functions."""

import pandas as pd
import streamlit as st
import altair as alt


def display_total_cost_line(
    df: pd.DataFrame, date_col: str, value_col: str, recipe_col: str = "recipe_name"
):
    """Display a multi-recipe line chart with hover tooltip and legend."""
    if date_col not in df.columns or value_col not in df.columns:
        st.info(f"Missing required columns: `{date_col}` or `{value_col}`.")
        return
    if recipe_col not in df.columns:
        st.info(f"Missing recipe column `{recipe_col}` — cannot group by recipe.")
        return

    data = df[[date_col, value_col, recipe_col]].copy()
    data[date_col] = pd.to_datetime(data[date_col], errors="coerce")
    data[value_col] = pd.to_numeric(data[value_col], errors="coerce")
    data = data.dropna().sort_values([recipe_col, date_col])

    if data.empty:
        st.info("No valid data to plot.")
        return

    data = (
        data.groupby([recipe_col, date_col], as_index=False)[value_col]
        .mean()
        .sort_values([recipe_col, date_col])
    )

    chart = (
        alt.Chart(data)
        .mark_line(point=True)
        .encode(
            x=alt.X(date_col, title="Week"),
            y=alt.Y(value_col, title="Total Cost (€)"),
            color=alt.Color(recipe_col, title="Recipe"),
            tooltip=[recipe_col, date_col, value_col],
        )
        .properties(height=400)
        .interactive()
    )

    st.altair_chart(chart, use_container_width=True)


def display_cost_breakdown(df: pd.DataFrame):
    """Display a horizontal bar chart of ingredient cost breakdown."""
    required = {"product_name", "item_cost", "cost_pct"}
    if not required.issubset(df.columns):
        return

    data = df.copy()

    if "recipe_name" in data.columns:
        recipes = sorted(data["recipe_name"].dropna().unique())
        if len(recipes) > 1:
            selected = st.selectbox("Recipe", recipes)
            data = data[data["recipe_name"] == selected]

    data = data[["product_name", "item_cost", "cost_pct"]].copy()
    data["item_cost"] = pd.to_numeric(data["item_cost"], errors="coerce")
    data["cost_pct"] = pd.to_numeric(data["cost_pct"], errors="coerce")
    data = data.dropna()

    if data.empty:
        return

    chart = (
        alt.Chart(data)
        .mark_bar()
        .encode(
            x=alt.X("item_cost:Q", title="Cost (€)"),
            y=alt.Y("product_name:N", title="Ingredient", sort="-x"),
            color=alt.Color("product_name:N", legend=None),
            tooltip=["product_name", "item_cost", "cost_pct"],
        )
        .properties(height=max(len(data) * 40, 200))
    )

    st.altair_chart(chart, use_container_width=True)


def _top_movers(data: pd.DataFrame, n: int = 10) -> list[str]:
    """Return product names with the largest cumulative absolute price change."""
    movers = (
        data.groupby("product_name")["price_change"]
        .apply(lambda s: s.abs().sum())
        .sort_values(ascending=False)
    )
    return movers.head(n).index.tolist()


def display_price_changes(df: pd.DataFrame, engine=None):
    """Display top movers with full price history from fct_products."""
    from bonuschef.portal.db import read_product_prices

    required = {"product_name", "snapshot_timestamp", "price_change", "pct_change"}
    if not required.issubset(df.columns):
        return

    changes = df[["product_name", "price_change"]].copy()
    changes["price_change"] = pd.to_numeric(changes["price_change"], errors="coerce")
    changes = changes.dropna()

    if changes.empty:
        return

    top = _top_movers(changes)
    all_products = sorted(changes["product_name"].unique())

    selected = st.multiselect(
        "Products to display (top 10 movers pre-selected)",
        options=all_products,
        default=top,
    )

    if not selected:
        st.info("Select at least one product to display the chart.")
        return

    if engine is None:
        st.warning("Cannot load full price history without database connection.")
        return

    history = read_product_prices(engine, tuple(selected))

    if history.empty:
        st.info("No price history found for the selected products.")
        return

    history["snapshot_timestamp"] = pd.to_datetime(
        history["snapshot_timestamp"], errors="coerce"
    )
    history["price"] = pd.to_numeric(history["price"], errors="coerce")
    history = history.dropna().sort_values(["product_name", "snapshot_timestamp"])

    chart = (
        alt.Chart(history)
        .mark_line(point=True)
        .encode(
            x=alt.X("snapshot_timestamp:T", title="Date"),
            y=alt.Y("price:Q", title="Price (€)"),
            color=alt.Color("product_name:N", title="Product"),
            tooltip=["product_name", "snapshot_timestamp", "price"],
        )
        .properties(height=400)
        .interactive()
    )

    st.altair_chart(chart, use_container_width=True)
