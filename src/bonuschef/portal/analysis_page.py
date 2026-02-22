"""Analysis page — product price changes, price history, and bonus price check."""

import altair as alt
import pandas as pd
import streamlit as st

from bonuschef.portal.db import get_engine, read_bonus_price_comparison, read_price_changes
from bonuschef.portal.ui import display_price_changes


def _render_price_changes_table(changes_df):
    """Display recent price changes in a formatted table."""
    st.subheader("Recent Price Changes")

    display_df = changes_df[
        [
            "product_name",
            "snapshot_timestamp",
            "prev_price",
            "new_price",
            "price_change",
            "pct_change",
        ]
    ].copy()
    display_df = display_df.rename(
        columns={
            "product_name": "Product",
            "snapshot_timestamp": "Date",
            "prev_price": "Previous (\u20ac)",
            "new_price": "New (\u20ac)",
            "price_change": "Change (\u20ac)",
            "pct_change": "Change (%)",
        }
    )

    st.dataframe(
        display_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Previous (\u20ac)": st.column_config.NumberColumn(format="\u20ac%.2f"),
            "New (\u20ac)": st.column_config.NumberColumn(format="\u20ac%.2f"),
            "Change (\u20ac)": st.column_config.NumberColumn(format="\u20ac%.2f"),
            "Change (%)": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )


def _render_price_history(engine, changes_df):
    """Display top movers chart and product price history."""
    st.subheader("Price History")
    display_price_changes(changes_df, engine=engine)


def _render_bonus_price_check(engine):
    """Show bonus vs tracked price comparison across all products."""
    bonus_df = read_bonus_price_comparison(engine)
    if bonus_df.empty:
        return

    st.subheader("Bonus Price Check")
    st.caption(
        "Compares AH's claimed regular price with the actual tracked price "
        "to detect inflated \"before\" prices."
    )

    total = len(bonus_df)
    inflated = bonus_df["is_inflated"].sum()
    inflated_df = bonus_df[bonus_df["is_inflated"]].copy()
    avg_inflation = inflated_df["price_inflation"].mean() if not inflated_df.empty else 0

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Bonus products matched", total)
    with col2:
        st.metric("Inflated pricing", f"{inflated} ({100 * inflated / total:.0f}%)")
    with col3:
        st.metric("Avg. inflation", f"\u20ac{avg_inflation:.2f}")

    # Bar chart — top 15 products by price inflation
    if not inflated_df.empty:
        chart_data = inflated_df.nlargest(15, "price_inflation")[
            ["product_name", "price_inflation", "tracked_price", "ah_price"]
        ].copy()
        for col in ["price_inflation", "tracked_price", "ah_price"]:
            chart_data[col] = pd.to_numeric(chart_data[col], errors="coerce")

        chart = (
            alt.Chart(chart_data)
            .mark_bar()
            .encode(
                x=alt.X("price_inflation:Q", title="Price Inflation (\u20ac)"),
                y=alt.Y("product_name:N", title="Product", sort="-x"),
                tooltip=[
                    alt.Tooltip("product_name:N", title="Product"),
                    alt.Tooltip("tracked_price:Q", title="Tracked price", format=".2f"),
                    alt.Tooltip("ah_price:Q", title="AH price", format=".2f"),
                    alt.Tooltip("price_inflation:Q", title="Inflation", format=".2f"),
                ],
            )
            .properties(height=max(len(chart_data) * 40, 200))
        )

        st.altair_chart(chart, use_container_width=True)

    # Full table
    display_df = bonus_df[
        [
            "product_name",
            "tracked_price",
            "ah_price",
            "bonus_price",
            "price_inflation",
            "real_savings",
            "advertised_savings",
            "bonus_mechanism",
            "is_inflated",
        ]
    ].copy()
    display_df = display_df.rename(
        columns={
            "product_name": "Product",
            "tracked_price": "Tracked (\u20ac)",
            "ah_price": "AH Price (\u20ac)",
            "bonus_price": "Bonus (\u20ac)",
            "price_inflation": "Inflation (\u20ac)",
            "real_savings": "Real Savings (\u20ac)",
            "advertised_savings": "AH Claims (\u20ac)",
            "bonus_mechanism": "Mechanism",
            "is_inflated": "Inflated?",
        }
    )

    st.dataframe(
        display_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Tracked (\u20ac)": st.column_config.NumberColumn(format="\u20ac%.2f"),
            "AH Price (\u20ac)": st.column_config.NumberColumn(format="\u20ac%.2f"),
            "Bonus (\u20ac)": st.column_config.NumberColumn(format="\u20ac%.2f"),
            "Inflation (\u20ac)": st.column_config.NumberColumn(format="\u20ac%.2f"),
            "Real Savings (\u20ac)": st.column_config.NumberColumn(format="\u20ac%.2f"),
            "AH Claims (\u20ac)": st.column_config.NumberColumn(format="\u20ac%.2f"),
        },
    )


def render_analysis():
    st.title("Price Analysis")

    try:
        engine = get_engine()
    except Exception as e:
        st.error(f"Database connection error: {e}")
        return

    changes_df = read_price_changes(engine)

    if changes_df.empty:
        st.info("No price changes recorded yet.")
        return

    _render_price_changes_table(changes_df)
    _render_price_history(engine, changes_df)
    _render_bonus_price_check(engine)
