"""Database file with helper functions."""

import os

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

from bonuschef.config import DatabaseConfig


# Pipelines run hourly at best and recipe costs only change on a dbt run, so a
# 60-second lifetime re-queried unchanged data constantly. Explicit .clear()
# calls on the refresh paths keep a manual refresh immediate.
_CACHE_TTL_S = 900

# Upper bound for the diagnostic surfaces, which are not the product.
_DIAGNOSTIC_ROW_LIMIT = 500


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


@st.cache_data(ttl=_CACHE_TTL_S)
def read_recipe_summary(_engine) -> pd.DataFrame:
    """Fetch current recipe costs from fct_recipe_cost_latest."""
    schema = _get_schema()
    sql = text(f"""
        SELECT
            recipe_id, recipe_name, servings,
            total_cost, cost_per_serving, partial_cost_observed,
            items_total, items_priced, items_unresolved, price_coverage
        FROM "{schema}"."fct_recipe_cost_latest"
        ORDER BY recipe_name
    """)
    with _engine.begin() as conn:
        return pd.read_sql_query(sql, conn)


@st.cache_data(ttl=_CACHE_TTL_S)
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


@st.cache_data(ttl=_CACHE_TTL_S)
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


@st.cache_data(ttl=_CACHE_TTL_S)
def read_recipe_breakdown_bonus(_engine, recipe_id: int) -> pd.DataFrame:
    """Fetch ingredient breakdown with bonus info for a recipe."""
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
            b.is_on_bonus,
            b.bonus_mechanism,
            b.price_before_bonus,
            b.bonus_price,
            b.advertised_savings,
            b.real_savings,
            d.product_url,
            d.image_url
        FROM "{schema}"."fct_recipe_cost_breakdown_bonus" AS b
        LEFT JOIN "{schema}"."dim_product" AS d
            ON b.product_link = d.product_link
        WHERE b.recipe_id = :recipe_id
        ORDER BY b.item_cost DESC
    """)
    with _engine.begin() as conn:
        return pd.read_sql_query(sql, conn, params={"recipe_id": recipe_id})


@st.cache_data(ttl=_CACHE_TTL_S)
def read_recipe_bonus_summary(_engine) -> pd.DataFrame:
    """Fetch bonus summary per recipe: how many ingredients on bonus, total savings."""
    schema = _get_schema()
    sql = text(f"""
        SELECT
            recipe_id,
            recipe_name,
            COUNT(*) FILTER (WHERE is_on_bonus) AS bonus_count,
            COUNT(*) AS total_ingredients,
            COALESCE(SUM(real_savings), 0) AS total_real_savings,
            COALESCE(SUM(advertised_savings), 0) AS total_advertised_savings
        FROM "{schema}"."fct_recipe_cost_breakdown_bonus"
        GROUP BY recipe_id, recipe_name
        ORDER BY total_real_savings DESC
    """)
    with _engine.begin() as conn:
        return pd.read_sql_query(sql, conn)


# ---------------------------------------------------------------------------
# Mart queries — analysis pages
# ---------------------------------------------------------------------------


@st.cache_data(ttl=_CACHE_TTL_S)
def read_bonus_price_comparison(_engine) -> pd.DataFrame:
    """Fetch bonus vs tracked price comparison for all matched products."""
    schema = _get_schema()
    sql = text(f"""
        SELECT
            product_link, product_name,
            tracked_price, ah_price, bonus_price,
            bonus_mechanism, bonus_start_date, bonus_end_date,
            price_inflation, real_savings, advertised_savings,
            is_inflated
        FROM "{schema}"."fct_bonus_price_comparison"
        ORDER BY price_inflation DESC NULLS LAST
    """)
    with _engine.begin() as conn:
        return pd.read_sql_query(sql, conn)


@st.cache_data(ttl=_CACHE_TTL_S)
def read_price_changes(_engine) -> pd.DataFrame:
    """Fetch the most recent product price changes.

    Bounded deliberately: this used to return every change ever recorded to
    render a view of the newest handful.
    """
    schema = _get_schema()
    sql = text(f"""
        SELECT
            product_link, product_name,
            prev_snapshot_timestamp, snapshot_timestamp,
            prev_price, new_price, price_change, pct_change
        FROM "{schema}"."fct_product_price_changes"
        ORDER BY snapshot_timestamp DESC
        LIMIT :limit
    """)
    with _engine.begin() as conn:
        return pd.read_sql_query(sql, conn, params={"limit": _DIAGNOSTIC_ROW_LIMIT})


@st.cache_data(ttl=_CACHE_TTL_S)
def read_product_prices(_engine, product_names: tuple[str, ...]) -> pd.DataFrame:
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


@st.cache_data(ttl=_CACHE_TTL_S)
def list_products(_engine) -> pd.DataFrame:
    """Return all current products with latest price and image, sorted by name.

    dim_product now carries price and image_url directly, so this is a single
    table scan rather than a DISTINCT ON over 1.19M rows to re-derive a value
    the dimension was already built from. Carrying image_url is what lets the
    recipe builder stop fetching every product image from ah.nl at render time.
    """
    schema = _get_schema()
    sql = text(f"""
        SELECT
            d.product_link, d.product_url, d.product_name,
            d.price, d.image_url
        FROM "{schema}"."dim_product" AS d
        ORDER BY d.product_name
    """)
    with _engine.begin() as conn:
        return pd.read_sql_query(sql, conn)


@st.cache_data(ttl=_CACHE_TTL_S)
def read_store_clearance(_engine) -> pd.DataFrame:
    """Fetch current store clearance ("laatste kans koopjes")."""
    schema = _get_schema()
    sql = text(f"""
        SELECT
            product_name, brand, sales_unit_size, category_title,
            markdown_type, markdown_percentage, markdown_expiration_date,
            stock, price_was, price_now, markdown_amount,
            tracked_price, real_savings_vs_tracked, image_url, scraped_at
        FROM "{schema}"."fct_store_clearance"
        -- Lowest stock first: at 17:30 the deciding question is whether it
        -- will still be there, not which percentage is largest.
        ORDER BY
            stock ASC NULLS LAST,
            markdown_percentage DESC NULLS LAST,
            markdown_amount DESC NULLS LAST
    """)
    with _engine.begin() as conn:
        return pd.read_sql_query(sql, conn)


@st.cache_data(ttl=_CACHE_TTL_S)
def read_last_scrape_time(_engine) -> pd.Timestamp | None:
    """When the store was last scraped, whether or not it found any items.

    Sourced from the append-only history rather than the current-items mart, so
    a scrape that succeeded and found nothing is still dated. Without this, an
    empty mart is indistinguishable from one whose pipeline died months ago —
    and an expired member token is the documented way that happens.
    """
    schema = _get_schema()
    sql = text(f'SELECT MAX(scraped_at) FROM "{schema}"."fct_store_clearance_history"')
    with _engine.begin() as conn:
        value = conn.execute(sql).scalar()
    return None if value is None else pd.to_datetime(value, utc=True)


# ---------------------------------------------------------------------------
# Recipe table management (portal writes to public schema)
# ---------------------------------------------------------------------------


def ensure_recipe_tables(_engine) -> None:
    """Create recipe tables in public schema if they don't exist (fresh environments)."""
    with _engine.begin() as conn:
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS public.recipes (
                recipe_id INTEGER NOT NULL,
                recipe_name TEXT NOT NULL,
                servings INTEGER NOT NULL
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS public.recipe_ingredients (
                recipe_id INTEGER NOT NULL,
                product_name TEXT NOT NULL,
                product_link TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                valid_from TIMESTAMP,
                valid_to TIMESTAMP
            )
        """)
        )


def ensure_catalogue_tables(_engine) -> None:
    """Create the tables an adopted recipe needs.

    Separate from ``public.recipes`` because that table cannot hold one:
    ``quantity`` is INTEGER and an AH recipe asks for 1.5 courgettes, and
    ``product_link NOT NULL`` makes an unresolved ingredient unrepresentable —
    the very state the specification requires us to record rather than drop.

    Owned by the portal. dbt reads these as sources and creates none of them:
    two owners for one schema is the defect that removing dbt's dlt DDL fixed,
    and a user's confirmed resolution survives ``--full-refresh`` precisely
    because dbt cannot touch it.
    """
    with _engine.begin() as conn:
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS public.ah_recipes (
                recipe_id      BIGINT PRIMARY KEY,
                title          TEXT    NOT NULL,
                servings       INTEGER NOT NULL,
                url            TEXT,
                image_url      TEXT,
                cook_time_min  INTEGER,
                adopted_at     TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS public.ah_recipe_ingredients (
                recipe_id    BIGINT  NOT NULL
                    REFERENCES public.ah_recipes(recipe_id) ON DELETE CASCADE,
                line_no      INTEGER NOT NULL,
                concept_id   BIGINT  NOT NULL,
                concept_name TEXT    NOT NULL,
                quantity     NUMERIC NOT NULL,
                unit         TEXT    NOT NULL DEFAULT '',
                raw_text     TEXT    NOT NULL DEFAULT '',
                PRIMARY KEY (recipe_id, line_no)
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS public.ah_ingredient_products (
                concept_id    BIGINT NOT NULL,
                product_link  TEXT   NOT NULL,
                product_name  TEXT   NOT NULL,
                -- NULL means the matcher proposed it and nobody has looked.
                -- A confirmed row must never be overwritten by a re-run.
                confirmed_at  TIMESTAMPTZ,
                proposed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (concept_id, product_link)
            )
        """)
        )
        conn.execute(
            text("""
            -- 6 of 467 sampled ingredient names carry two concept ids
            -- (courgette is both 1853 and 219282). Without this, resolving an
            -- ingredient once fails to serve both for about one in seventy-eight.
            CREATE TABLE IF NOT EXISTS public.ah_ingredient_aliases (
                concept_id           BIGINT PRIMARY KEY,
                canonical_concept_id BIGINT NOT NULL
            )
        """)
        )


def adopted_recipe_rows(recipe) -> tuple[dict, list[dict]]:
    """Split a Recipe into its header and ingredient rows.

    Pure, so the interesting half is testable without a database.
    """
    header = {
        "recipe_id": recipe.recipe_id,
        "title": recipe.title,
        "servings": recipe.servings,
        "url": recipe.url,
        "image_url": recipe.image_url,
        "cook_time_min": recipe.cook_time_min,
    }
    lines = [
        {
            "recipe_id": recipe.recipe_id,
            "line_no": n,
            "concept_id": ing.concept_id,
            "concept_name": ing.name,
            "quantity": ing.quantity,
            "unit": ing.unit,
            "raw_text": ing.raw_text,
        }
        for n, ing in enumerate(recipe.ingredients)
    ]
    return header, lines


def save_adopted_recipe(_engine, recipe) -> bool:
    """Store an adopted recipe. Returns False if it was already there.

    Idempotence is a database guarantee rather than a UI check: AH has four
    recipes called "Zuurkoolstamppot" and they are genuinely different, so the
    key is AH's id and not the title.
    """
    header, lines = adopted_recipe_rows(recipe)
    with _engine.begin() as conn:
        inserted = conn.execute(
            text("""
                INSERT INTO public.ah_recipes
                    (recipe_id, title, servings, url, image_url, cook_time_min)
                VALUES (:recipe_id, :title, :servings, :url, :image_url, :cook_time_min)
                ON CONFLICT (recipe_id) DO NOTHING
                RETURNING recipe_id
            """),
            header,
        ).scalar()
        if inserted is None:
            return False
        for line in lines:
            conn.execute(
                text("""
                    INSERT INTO public.ah_recipe_ingredients
                        (recipe_id, line_no, concept_id, concept_name,
                         quantity, unit, raw_text)
                    VALUES (:recipe_id, :line_no, :concept_id, :concept_name,
                            :quantity, :unit, :raw_text)
                    ON CONFLICT (recipe_id, line_no) DO NOTHING
                """),
                line,
            )
    return True


def is_adopted(_engine, ah_recipe_id: int) -> bool:
    with _engine.begin() as conn:
        return (
            conn.execute(
                text("SELECT 1 FROM public.ah_recipes WHERE recipe_id = :id"),
                {"id": ah_recipe_id},
            ).scalar()
            is not None
        )


def propose_products(_engine, proposals: list[dict]) -> None:
    """Record matcher proposals, never overwriting a person's decision.

    The WHERE on the DO UPDATE is the whole guarantee: without it, re-running
    the matcher after a catalogue refresh would silently revert every
    correction ever made.
    """
    if not proposals:
        return
    with _engine.begin() as conn:
        for row in proposals:
            conn.execute(
                text("""
                    INSERT INTO public.ah_ingredient_products AS p
                        (concept_id, product_link, product_name)
                    VALUES (:concept_id, :product_link, :product_name)
                    ON CONFLICT (concept_id, product_link) DO UPDATE
                    SET product_name = EXCLUDED.product_name
                    WHERE p.confirmed_at IS NULL
                """),
                row,
            )


def next_recipe_id(_engine) -> int:
    """Return the next available recipe_id."""
    with _engine.begin() as conn:
        result = conn.execute(
            text("SELECT COALESCE(MAX(recipe_id), 0) FROM public.recipes")
        )
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
            text(
                "INSERT INTO public.recipes (recipe_id, recipe_name, servings) VALUES (:id, :name, :servings)"
            ),
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
                {
                    "rid": recipe_id,
                    "pname": product_name,
                    "plink": product_link,
                    "qty": quantity,
                },
            )


def ensure_product_images_table(_engine) -> None:
    """Create product_images table if it doesn't exist (fresh environments)."""
    with _engine.begin() as conn:
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS public.product_images (
                product_link TEXT PRIMARY KEY,
                image_url TEXT NOT NULL
            )
        """)
        )


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
