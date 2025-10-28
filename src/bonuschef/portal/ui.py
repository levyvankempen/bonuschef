"""Streamlit UI helper functions."""

import os
import pandas as pd
import streamlit as st

from bonuschef.portal.db import list_schemas, list_tables


def sidebar_controls(_engine):
    st.sidebar.header("Data source")
    default_schema = os.getenv("TARGET_SCHEMA") or "public_marts"
    default_table = os.getenv("PORTAL_DEFAULT_TABLE") or "fct_recipe_cost_history"

    schemas = list_schemas(_engine)
    if not schemas:
        st.sidebar.error("No schemas found.")
        st.stop()

    if default_schema not in schemas:
        default_schema = schemas[0]
    schema = st.sidebar.selectbox(
        "Schema", schemas, index=schemas.index(default_schema)
    )

    tables = list_tables(_engine, schema)
    if not tables:
        st.sidebar.error("No tables found in schema.")
        st.stop()

    if default_table not in tables:
        default_table = tables[0]
    table = st.sidebar.selectbox("Table", tables, index=tables.index(default_table))

    st.sidebar.divider()
    st.sidebar.header("Chart options")
    date_candidates = [c for c in ["snapshot_timestamp"]]
    date_col = st.sidebar.text_input(
        "Date column (for line chart)", value=date_candidates[0]
    )
    freq = st.sidebar.selectbox(
        "Resample frequency", ["D", "W", "M", "Q", "Y"], index=2
    )
    metric_col = st.sidebar.text_input("Metric column", value="total_cost")
    agg = st.sidebar.selectbox("Aggregation", ["mean", "sum", "median"], index=0)

    return schema, table, date_col, freq, metric_col, agg


def display_table(df: pd.DataFrame):
    st.caption(f"{len(df):,} rows")
    st.dataframe(df, use_container_width=True, hide_index=True)


def display_total_cost_line(
    df: pd.DataFrame, date_col: str, value_col: str, freq: str, agg: str
):
    if date_col not in df.columns:
        st.info(
            f"Column `{date_col}` not in table; update the Date column in the sidebar."
        )
        return
    if value_col not in df.columns:
        st.info(
            f"Column `{value_col}` not in table; update the Metric column in the sidebar."
        )
        return

    s = pd.to_datetime(df[date_col], errors="coerce")
    y = pd.to_numeric(df[value_col], errors="coerce")
    data = pd.DataFrame({date_col: s, value_col: y}).dropna()

    if data.empty:
        st.info("No valid (date, value) rows to plot.")
        return

    data = data.sort_values(date_col).set_index(date_col)

    if agg == "sum":
        series = data[value_col].resample(freq).sum()
    elif agg == "mean":
        series = data[value_col].resample(freq).mean()
    else:
        series = data[value_col].resample(freq).median()

    st.line_chart(series, use_container_width=True)
