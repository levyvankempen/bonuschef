"""Database file with helper functions"""

import os
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text


@st.cache_resource
def get_engine():
    host = os.getenv("PG_HOST")
    port = os.getenv("PG_PORT")
    db = os.getenv("PG_DB")
    user = os.getenv("PG_USER")
    pwd = os.getenv("PG_PASSWORD")
    sslmode = os.getenv("PG_SSLMODE", "prefer")

    if not all([host, port, db, user, pwd]):
        raise RuntimeError(
            "Missing one or more PG_* environment variables: "
            "PG_HOST, PG_PORT, PG_DB, PG_USER, PG_PASSWORD"
        )

    url = f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}?sslmode={sslmode}"
    return create_engine(url, pool_pre_ping=True, pool_size=3, max_overflow=2)


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
