"""Main file for running the app."""

import streamlit as st

from bonuschef.portal.db import get_engine, read_table
from bonuschef.portal.ui import (
    display_cost_breakdown,
    display_price_changes,
    display_table,
    display_total_cost_line,
    sidebar_controls,
)


def render_app():
    st.set_page_config(
        page_title="BonusChef Data Portal",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.title("BonusChef Data Portal")
    st.write("Simple viewer for dbt-created tables in PostgreSQL.")

    try:
        engine = get_engine()
    except Exception as e:
        st.error(f"Database connection error: {e}")
        st.stop()

    schema, table = sidebar_controls(engine)

    with st.spinner(f"Loading `{schema}.{table}`..."):
        try:
            df = read_table(engine, schema, table)
        except Exception as e:
            st.error(f"Query failed: {e}")
            st.stop()

    display_table(df)

    cost_col = None
    if "total_cost_observed" in df.columns:
        cost_col = "total_cost_observed"
    elif "total_cost" in df.columns:
        cost_col = "total_cost"

    if cost_col and "snapshot_timestamp" in df.columns and "recipe_name" in df.columns:
        st.subheader("Total cost per recipe over time")
        display_total_cost_line(
            df,
            date_col="snapshot_timestamp",
            value_col=cost_col,
            recipe_col="recipe_name",
        )

    if "cost_pct" in df.columns and "item_cost" in df.columns:
        st.subheader("Ingredient cost breakdown")
        display_cost_breakdown(df)

    if "price_change" in df.columns and "pct_change" in df.columns:
        st.subheader("Price history")
        display_price_changes(df, engine=engine, schema=schema)


def main():
    render_app()


if __name__ == "__main__":
    main()
