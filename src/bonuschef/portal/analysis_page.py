"""Analysis page — product price changes and price history."""

import streamlit as st

from bonuschef.portal.db import get_engine, read_price_changes
from bonuschef.portal.ui import display_price_changes


def _render_price_changes_table(changes_df):
    """Display recent price changes in a formatted table."""
    st.subheader("Recent Price Changes")

    display_df = changes_df[[
        "product_name", "snapshot_timestamp",
        "prev_price", "new_price", "price_change", "pct_change",
    ]].copy()
    display_df = display_df.rename(columns={
        "product_name": "Product",
        "snapshot_timestamp": "Date",
        "prev_price": "Previous (€)",
        "new_price": "New (€)",
        "price_change": "Change (€)",
        "pct_change": "Change (%)",
    })

    st.dataframe(
        display_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Previous (€)": st.column_config.NumberColumn(format="€%.2f"),
            "New (€)": st.column_config.NumberColumn(format="€%.2f"),
            "Change (€)": st.column_config.NumberColumn(format="€%.2f"),
            "Change (%)": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )


def _render_price_history(engine, changes_df):
    """Display top movers chart and product price history."""
    st.subheader("Price History")
    display_price_changes(changes_df, engine=engine)


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
