"""Streamlit UI helper functions."""

import os
import pandas as pd
import streamlit as st
import altair as alt

from bonuschef.portal.db import list_schemas, list_tables


def sidebar_controls(_engine):
    """Sidebar with only schema and table selection (no chart options)."""
    st.sidebar.header("Data source")
    default_schema = os.getenv("TARGET_SCHEMA") or "public_marts"
    default_table = os.getenv("PORTAL_DEFAULT_TABLE") or "fct_recipe_cost_history"

    schemas = list_schemas(_engine)
    if not schemas:
        st.sidebar.error("No schemas found.")
        st.stop()

    if default_schema not in schemas:
        default_schema = schemas[0]
    schema = st.sidebar.selectbox("Schema", schemas, index=schemas.index(default_schema))

    tables = list_tables(_engine, schema)
    if not tables:
        st.sidebar.error("No tables found in schema.")
        st.stop()

    if default_table not in tables:
        default_table = tables[0]
    table = st.sidebar.selectbox("Table", tables, index=tables.index(default_table))

    return schema, table



def display_table(df: pd.DataFrame):
    """Display dataframe ordered by snapshot_timestamp DESC, hide recipe_id, and wrap in expander."""
    df = df.copy()

    if "recipe_id" in df.columns:
        df = df.drop(columns=["recipe_id"])

    if "snapshot_timestamp" in df.columns:
        df["snapshot_timestamp"] = pd.to_datetime(df["snapshot_timestamp"], errors="coerce")
        df = df.sort_values("snapshot_timestamp", ascending=False)

    with st.expander(f"Show table ({len(df):,} rows)", expanded=False):
        st.dataframe(df, use_container_width=True, hide_index=True)



def display_total_cost_line(df: pd.DataFrame, date_col: str, value_col: str, recipe_col: str = "recipe_name"):
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
