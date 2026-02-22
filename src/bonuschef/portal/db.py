"""Database file with helper functions."""

import os

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

from bonuschef.config import DatabaseConfig


def _get_schema() -> str:
    """Return the target dbt schema name (never exposed to UI)."""
    return os.getenv("TARGET_SCHEMA", "public_marts")


@st.cache_resource
def get_engine():
    cfg = DatabaseConfig.from_env()
    return create_engine(cfg.url, pool_pre_ping=True, pool_size=3, max_overflow=2)


# ---------------------------------------------------------------------------
# Mart queries — recipe pages
# ---------------------------------------------------------------------------


@st.cache_data(ttl=60)
def read_recipe_summary(_engine) -> pd.DataFrame:
    """Fetch current recipe costs from fct_recipe_cost_latest."""
    schema = _get_schema()
    sql = text(f"""
        SELECT recipe_id, recipe_name, servings, total_cost, cost_per_serving
        FROM "{schema}"."fct_recipe_cost_latest"
        ORDER BY recipe_name
    """)
    with _engine.begin() as conn:
        return pd.read_sql_query(sql, conn)


@st.cache_data(ttl=60)
def read_recipe_cost_history(_engine) -> pd.DataFrame:
    """Fetch historical recipe costs from fct_recipe_cost_history."""
    schema = _get_schema()
    sql = text(f"""
        SELECT
            recipe_id, recipe_name, servings,
            snapshot_timestamp, total_cost_observed,
            price_coverage, cost_per_serving_strict
        FROM "{schema}"."fct_recipe_cost_history"
        ORDER BY recipe_name, snapshot_timestamp
    """)
    with _engine.begin() as conn:
        return pd.read_sql_query(sql, conn)


@st.cache_data(ttl=60)
def read_recipe_breakdown(_engine, recipe_id: int) -> pd.DataFrame:
    """Fetch ingredient breakdown for a recipe, joined with dim_product for images."""
    schema = _get_schema()
    sql = text(f"""
        SELECT
            b.recipe_id,
            b.recipe_name,
            b.product_name,
            b.product_link,
            b.quantity,
            b.price,
            b.item_cost,
            b.cost_pct,
            d.product_url,
            d.image_url
        FROM "{schema}"."fct_recipe_cost_breakdown" AS b
        LEFT JOIN "{schema}"."dim_product" AS d
            ON b.product_link = d.product_link
        WHERE b.recipe_id = :recipe_id
        ORDER BY b.item_cost DESC
    """)
    with _engine.begin() as conn:
        return pd.read_sql_query(sql, conn, params={"recipe_id": recipe_id})


# ---------------------------------------------------------------------------
# Mart queries — analysis pages
# ---------------------------------------------------------------------------


@st.cache_data(ttl=60)
def read_price_changes(_engine) -> pd.DataFrame:
    """Fetch all product price changes from fct_product_price_changes."""
    schema = _get_schema()
    sql = text(f"""
        SELECT
            product_link, product_name,
            prev_snapshot_timestamp, snapshot_timestamp,
            prev_price, new_price, price_change, pct_change
        FROM "{schema}"."fct_product_price_changes"
        ORDER BY snapshot_timestamp DESC
    """)
    with _engine.begin() as conn:
        return pd.read_sql_query(sql, conn)


@st.cache_data(ttl=60)
def read_product_prices(
    _engine, product_names: tuple[str, ...]
) -> pd.DataFrame:
    """Fetch full price history from fct_products for specific products."""
    schema = _get_schema()
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
def list_products(_engine) -> pd.DataFrame:
    """Return all current products with latest price, sorted by name."""
    schema = _get_schema()
    sql = text(f"""
        SELECT d.product_link, d.product_url, d.product_name, lp.price
        FROM "{schema}"."dim_product" AS d
        INNER JOIN (
            SELECT DISTINCT ON (product_link) product_link, price
            FROM "{schema}"."fct_products"
            ORDER BY product_link, snapshot_timestamp DESC
        ) AS lp ON d.product_link = lp.product_link
        ORDER BY d.product_name
    """)
    with _engine.begin() as conn:
        return pd.read_sql_query(sql, conn)


# ---------------------------------------------------------------------------
# Recipe table management (portal writes to public schema)
# ---------------------------------------------------------------------------


def ensure_recipe_tables(_engine) -> None:
    """Create recipe tables in public schema if they don't exist (fresh environments)."""
    with _engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS public.recipes (
                recipe_id INTEGER NOT NULL,
                recipe_name TEXT NOT NULL,
                servings INTEGER NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS public.recipe_ingredients (
                recipe_id INTEGER NOT NULL,
                product_name TEXT NOT NULL,
                product_link TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                valid_from TIMESTAMP,
                valid_to TIMESTAMP
            )
        """))


def next_recipe_id(_engine) -> int:
    """Return the next available recipe_id."""
    with _engine.begin() as conn:
        result = conn.execute(text("SELECT COALESCE(MAX(recipe_id), 0) FROM public.recipes"))
        return result.scalar() + 1


def existing_recipe_names(_engine) -> set[str]:
    """Return all existing recipe names."""
    with _engine.begin() as conn:
        rows = conn.execute(text("SELECT recipe_name FROM public.recipes"))
        return {r[0].strip() for r in rows}


def insert_recipe(_engine, recipe_id: int, recipe_name: str, servings: int) -> None:
    """Insert a new recipe row."""
    with _engine.begin() as conn:
        conn.execute(
            text("INSERT INTO public.recipes (recipe_id, recipe_name, servings) VALUES (:id, :name, :servings)"),
            {"id": recipe_id, "name": recipe_name, "servings": servings},
        )


def insert_ingredients(
    _engine, recipe_id: int, ingredients: list[tuple[str, str, int]]
) -> None:
    """Insert ingredient rows. Each tuple is (product_name, product_link, quantity)."""
    with _engine.begin() as conn:
        for product_name, product_link, quantity in ingredients:
            conn.execute(
                text("""
                    INSERT INTO public.recipe_ingredients
                        (recipe_id, product_name, product_link, quantity, valid_from, valid_to)
                    VALUES (:rid, :pname, :plink, :qty, NULL, NULL)
                """),
                {"rid": recipe_id, "pname": product_name, "plink": product_link, "qty": quantity},
            )


def ensure_product_images_table(_engine) -> None:
    """Create product_images table if it doesn't exist (fresh environments)."""
    with _engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS public.product_images (
                product_link TEXT PRIMARY KEY,
                image_url TEXT NOT NULL
            )
        """))


def upsert_product_image(_engine, product_link: str, image_url: str) -> None:
    """Insert or update a product image URL."""
    with _engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO public.product_images (product_link, image_url)
                VALUES (:product_link, :image_url)
                ON CONFLICT (product_link) DO UPDATE SET image_url = EXCLUDED.image_url
            """),
            {"product_link": product_link, "image_url": image_url},
        )
