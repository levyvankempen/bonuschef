"""Main file for running the app."""

import streamlit as st
from bonuschef.portal.db import get_engine, read_table
from bonuschef.portal.ui import sidebar_controls, display_table, display_total_cost_line


def render_app():
    st.set_page_config(
        page_title="BonusChef • Data Portal",
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

    with st.spinner(f"Loading `{schema}.{table}`…"):
        try:
            df = read_table(engine, schema, table)
        except Exception as e:
            st.error(f"Query failed: {e}")
            st.stop()

    display_table(df)

    st.subheader("Total cost per recipe over time")
    display_total_cost_line(
        df,
        date_col="snapshot_timestamp",
        value_col="total_cost",
        recipe_col="recipe_name",
    )


def main():
    render_app()


if __name__ == "__main__":
    main()
