"""Database file with helper functions."""

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

from bonuschef.config import DatabaseConfig


@st.cache_resource
def get_engine():
    cfg = DatabaseConfig.from_env()
    return create_engine(cfg.url, pool_pre_ping=True, pool_size=3, max_overflow=2)


@st.cache_data(ttl=60)
def list_schemas(_engine) -> list[str]:
    q = text("""
        SELECT schema_name
        FROM information_schema.schemata
        WHERE schema_name NOT IN ('pg_catalog','information_schema')
        ORDER BY schema_name
    """)
    with _engine.begin() as conn:
        return [r[0] for r in conn.execute(q)]


@st.cache_data(ttl=60)
def list_tables(_engine, schema: str) -> list[str]:
    q = text("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = :schema AND table_type='BASE TABLE'
        ORDER BY table_name
    """)
    with _engine.begin() as conn:
        return [r[0] for r in conn.execute(q, {"schema": schema})]


@st.cache_data(ttl=60)
def read_product_prices(
    _engine, schema: str, product_names: tuple[str, ...]
) -> pd.DataFrame:
    """Fetch full price history from fct_products for specific products."""
    sql = text(f"""
        SELECT d.product_name, p.snapshot_timestamp, p.price
        FROM "{schema}"."fct_products" AS p
        INNER JOIN "{schema}"."dim_product" AS d
            ON p.product_link = d.product_link
        WHERE d.product_name IN :names
        ORDER BY d.product_name, p.snapshot_timestamp
    """)
    with _engine.begin() as conn:
        return pd.read_sql_query(sql, conn, params={"names": product_names})


@st.cache_data(ttl=60)
def read_table(_engine, schema: str, table: str) -> pd.DataFrame:
    valid_schemas = set(list_schemas(_engine))
    if schema not in valid_schemas:
        raise ValueError(f"Unknown schema: {schema}")

    valid_tables = set(list_tables(_engine, schema))
    if table not in valid_tables:
        raise ValueError(f"Unknown table in schema '{schema}': {table}")

    sql = f'SELECT * FROM "{schema}"."{table}" LIMIT 10000'
    with _engine.begin() as conn:
        return pd.read_sql_query(text(sql), conn)
