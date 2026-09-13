"""Streamlit UI helper functions."""

import pandas as pd
import streamlit as st
import altair as alt


def _top_movers(data: pd.DataFrame, n: int = 10) -> list[str]:
    """Return product names with the largest cumulative absolute price change."""
    movers = (
        data.assign(_abs_change=data["price_change"].abs())
        .groupby("product_name")["_abs_change"]
        .sum()
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

    st.altair_chart(chart)
