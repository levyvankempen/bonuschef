"""Database file with helper functions."""

import os

from typing import cast

import re

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
            -- The joins below existed for these five and selected none of them,
            -- so every ingredient rendered as resolved and priced: an
            -- unresolved one showed "EUR nan per stuk" instead of its badge,
            -- and the correction button never appeared because concept_id was
            -- always absent. The card above it said "1 van 2 zonder prijs" and
            -- the detail below contradicted it.
            b.item_key,
            b.item_label,
            b.is_unresolved,
            i.concept_id,
            r.review_state,
            d.product_url,
            d.image_url
        FROM "{schema}"."fct_recipe_cost_breakdown_bonus" AS b
        LEFT JOIN "{schema}"."dim_product" AS d
            ON b.product_link = d.product_link
        LEFT JOIN public.int_recipe_items_priced AS i
            ON b.recipe_id = i.recipe_id AND b.item_key = i.item_key
        LEFT JOIN public.ah_ingredient_review AS r
            ON i.concept_id = r.concept_id
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
            -- "A person looked and there is no such product" cannot be spelled
            -- as a NULL on the products table, and without it an ingredient
            -- like bospaddenstoelenfond stays outstanding forever and the list
            -- of work stops being a list of work. Absence of a row here means
            -- nobody has looked.
            CREATE TABLE IF NOT EXISTS public.ah_ingredient_review (
                concept_id   BIGINT PRIMARY KEY,
                review_state TEXT NOT NULL
                    CHECK (review_state IN ('resolved', 'none_exists')),
                reviewed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        )
        conn.execute(
            text("""
            -- A concept whose recorded products contradict what they are.
            --
            -- Separate from ah_ingredient_review rather than deleting the
            -- review row: "a person looked at this" and "this needs looking
            -- at again" are different facts, and destroying the first to
            -- express the second loses the record of who settled what.
            CREATE TABLE IF NOT EXISTS public.ah_ingredient_flags (
                concept_id BIGINT PRIMARY KEY,
                reason     TEXT NOT NULL,
                flagged_at TIMESTAMPTZ NOT NULL DEFAULT now()
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


def confirm_resolution(_engine, concept_id: int, product_links: list[str]) -> None:
    """Record a person's decision about which products satisfy an ingredient.

    Chosen products are marked confirmed; anything they deselected is removed.
    An empty choice is a legitimate answer - "nothing in the catalogue
    satisfies this" - and is recorded as such rather than rejected.
    """
    state = "resolved" if product_links else "none_exists"
    with _engine.begin() as conn:
        conn.execute(
            text("""
                DELETE FROM public.ah_ingredient_products
                WHERE concept_id = :concept_id
                  AND (CAST(:keep AS text[]) IS NULL
                       OR NOT (product_link = ANY(CAST(:keep AS text[]))))
            """),
            {"concept_id": concept_id, "keep": product_links or None},
        )
        for link in product_links:
            conn.execute(
                text("""
                    UPDATE public.ah_ingredient_products
                    SET confirmed_at = now()
                    WHERE concept_id = :concept_id AND product_link = :link
                """),
                {"concept_id": concept_id, "link": link},
            )
        conn.execute(
            text("""
                INSERT INTO public.ah_ingredient_review
                    (concept_id, review_state, reviewed_at)
                VALUES (:concept_id, :state, now())
                ON CONFLICT (concept_id) DO UPDATE
                SET review_state = EXCLUDED.review_state, reviewed_at = now()
            """),
            {"concept_id": concept_id, "state": state},
        )


def add_resolution_products(_engine, concept_id: int, products: list[dict]) -> None:
    """Attach products a person picked that the matcher had not proposed."""
    if not products:
        return
    with _engine.begin() as conn:
        for row in products:
            conn.execute(
                text("""
                    INSERT INTO public.ah_ingredient_products
                        (concept_id, product_link, product_name, confirmed_at)
                    VALUES (:concept_id, :product_link, :product_name, now())
                    ON CONFLICT (concept_id, product_link) DO UPDATE
                    SET confirmed_at = now()
                """),
                {"concept_id": concept_id, **row},
            )


@st.cache_data(ttl=_CACHE_TTL_S)
def read_unresolved_concepts(
    _engine, recipe_id: int | None = None, limit: int | None = None
) -> pd.DataFrame:
    """Ingredients nobody has settled yet.

    A concept a person examined and found nothing for is excluded: it has been
    answered, and leaving it here would make the outstanding list never empty.
    """
    # Both sources, or the queue is empty for everything the pool contributes -
    # which is almost all of it. Reading only adopted recipes made "Ingrediënten
    # koppelen" answer "alles is al gekoppeld" while 1,265 pool concepts waited.
    #
    # Ordered by how often the ingredient is used, most first: concept frequency
    # is steep, so the top of this list is where a few minutes buys the most.
    sql = text("""
        WITH lines AS (
            SELECT recipe_id, concept_id, concept_name
            FROM public.ah_recipe_ingredients
            UNION ALL
            SELECT recipe_id, concept_id, concept_name
            FROM public."ah__pool_recipe_ingredients"
        )
        SELECT i.concept_id,
               MIN(i.concept_name) AS concept_name,
               COUNT(*) AS uses,
               BOOL_OR(f.concept_id IS NOT NULL) AS is_flagged,
               MIN(f.reason) AS flag_reason
        FROM lines AS i
        LEFT JOIN public.ah_ingredient_review AS r
            ON i.concept_id = r.concept_id
        LEFT JOIN public.ah_ingredient_flags AS f
            ON i.concept_id = f.concept_id
        -- Never looked at, OR looked at and since found to contradict itself.
        -- Without the second arm a concept a person settled once could never
        -- come back, which is exactly the case where it is known to be wrong.
        WHERE (r.concept_id IS NULL OR f.concept_id IS NOT NULL)
          AND (CAST(:recipe_id AS bigint) IS NULL
               OR i.recipe_id = CAST(:recipe_id AS bigint))
        GROUP BY i.concept_id
        -- Flagged first: a known-wrong match costs more than an absent one,
        -- because it is silently priced into a recipe rather than shown as a gap.
        ORDER BY is_flagged DESC, uses DESC, concept_name ASC
        -- Bounded: the pool contributes over a thousand, and a dialog that
        -- renders them all is not a queue, it is a wall. The ordering above is
        -- what makes a bounded slice the useful one.
        LIMIT CAST(:limit AS integer)
    """)
    with _engine.begin() as conn:
        return pd.read_sql_query(
            sql, conn, params={"recipe_id": recipe_id, "limit": limit}
        )


@st.cache_data(ttl=_CACHE_TTL_S)
def read_concept_resolution(_engine, concept_id: int) -> pd.DataFrame:
    """Products attached to an ingredient, and whether a person chose them."""
    sql = text("""
        SELECT product_link, product_name, (confirmed_at IS NOT NULL) AS is_confirmed
        FROM public.ah_ingredient_products
        WHERE concept_id = :concept_id
        ORDER BY product_name
    """)
    with _engine.begin() as conn:
        return pd.read_sql_query(sql, conn, params={"concept_id": concept_id})


@st.cache_data(ttl=_CACHE_TTL_S)
def search_catalogue_products(_engine, term: str, limit: int = 20) -> pd.DataFrame:
    """Find a product by name, when the proposal is wrong or missing.

    Every word must appear, in any order, rather than the whole phrase in
    sequence. That is what makes an ingredient name usable as a search term:
    "(olijf)olie" as a phrase matches nothing, while its words find the olive
    oils. Punctuation is dropped for the same reason - AH writes "45+" and
    recipes write "(olijf)" and neither belongs in a product name.

    Shortest name first, because that is the ranking that puts "AH Courgette"
    above "AH Courgette spiraal" above a ready meal containing courgette.
    """
    words = [w for w in re.split(r"[^0-9a-zA-ZäëïöüéèáàçñÄËÏÖÜÉÈÁÀÇÑ]+", term) if w]
    if not words:
        empty: dict[str, list] = {"product_link": [], "product_name": [], "price": []}
        return pd.DataFrame(empty)

    schema = _get_schema()
    clauses = " AND ".join(f"product_name ILIKE :w{i}" for i in range(len(words)))
    sql = text(f"""
        SELECT product_link, product_name, price
        FROM "{schema}"."dim_product"
        WHERE {clauses}
        ORDER BY length(product_name), product_name
        LIMIT :limit
    """)
    params: dict[str, object] = {f"w{i}": f"%{w}%" for i, w in enumerate(words)}
    params["limit"] = limit
    with _engine.begin() as conn:
        return pd.read_sql_query(sql, conn, params=params)


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


@st.cache_data(ttl=_CACHE_TTL_S)
def read_recipe_opportunity(_engine) -> pd.DataFrame:
    """What is worth cooking today, and why every other recipe is not.

    Reads the whole table rather than filtering to the ranked rows. The mart
    keeps a row for every recipe in the pool precisely so the page can show how
    many it holds against how many it can rank, and a `WHERE opportunity_rank
    IS NOT NULL` here would throw that away at the last step.
    """
    schema = _get_schema()
    sql = text(f"""
        SELECT
            store_id, clearance_scraped_at, clearance_is_current,
            recipe_id, recipe_name, servings, source_kind, image_url, url,
            rating_average, rating_count,
            is_rankable, exclusion_reason, opportunity_rank,
            cost_ordinary, cost_today, cost_today_bonus_only,
            partial_cost_ordinary, partial_cost_today,
            partial_cost_today_bonus_only,
            cost_today_per_serving_bonus_only,
            saving_total, saving_bonus_only, conditional_saving,
            advertised_saving_total, saving_is_lower_bound,
            saving_covers_whole_packs, saving_pct, cost_today_per_serving,
            items_total, items_priced, items_unresolved, items_discounted,
            items_discounted_clearance, items_offer_withheld_stale,
            items_conditional_offer,
            min_stock_remaining, clearance_items_stock_unknown,
            earliest_expiry, clearance_items_expiry_unknown,
            has_insufficient_stock
        FROM "{schema}"."fct_recipe_opportunity"
        ORDER BY opportunity_rank ASC NULLS LAST, recipe_name ASC
    """)
    with _engine.begin() as conn:
        return pd.read_sql_query(sql, conn)


@st.cache_data(ttl=_CACHE_TTL_S)
def read_recipe_opportunity_items(_engine, recipe_id: int) -> pd.DataFrame:
    """The ingredients behind one recipe's ranking, discounted or not.

    Not filtered to discounted lines: "the rest of the basket did not move" is
    itself the answer to why a recipe is cheap by only so much, and an
    unresolved line is why it cannot be costed at all.
    """
    schema = _get_schema()
    sql = text(f"""
        SELECT
            item_key, concept_id, item_label, product_name,
            ordinary_product_link, offer_product_link,
            units, sales_unit_size, price_ordinary, price_today,
            price_today_bonus_only, item_cost_today_bonus_only,
            item_saving_bonus_only,
            item_cost_ordinary, item_cost_today, item_saving,
            item_conditional_saving, item_advertised_saving,
            offer_kind, offer_price, bonus_mechanism, conditional_mechanism,
            stock, expires_on, is_discounted, is_unresolved,
            reference_is_comparable, offer_withheld_stale_reference,
            ordinary_price_age_days
        FROM "{schema}"."fct_recipe_opportunity_items"
        WHERE recipe_id = CAST(:recipe_id AS bigint)
        ORDER BY item_saving DESC NULLS LAST, item_label ASC
    """)
    with _engine.begin() as conn:
        return pd.read_sql_query(sql, conn, params={"recipe_id": int(recipe_id)})


@st.cache_data(ttl=_CACHE_TTL_S)
def read_bonus_feed_loaded_at(_engine) -> pd.Timestamp | None:
    """When the promotional feed last loaded.

    The bonus feed is weekly, so it ages on a different clock from the hourly
    clearance scrape. Reporting one page's staleness using the other's rule
    would call the page stale every day of the week but one.
    """
    # The OLDER of the feed's load time and the mart's build time. Reading only
    # the source meant a successful dlt load followed by a failed dbt rebuild
    # left loaded_at fresh, the banner quiet, and every promotional figure on
    # the page frozen at whatever the last good build produced. The question
    # the banner answers is "how old is this answer", and an answer is only as
    # fresh as the older of the two.
    schema = _get_schema()
    sql = text(f"""
        SELECT LEAST(
            (SELECT MAX(loaded_at)::timestamptz FROM public."ah__bonus_products"),
            (SELECT MAX(built_at)::timestamptz
             FROM "{schema}"."fct_bonus_price_comparison")
        ) AS loaded_at
    """)
    try:
        with _engine.begin() as conn:
            value = pd.read_sql_query(sql, conn)["loaded_at"].iloc[0]
    except Exception:
        return None
    if pd.isna(value):
        return None
    return cast("pd.Timestamp", pd.Timestamp(value))


def ensure_verdict_table(_engine) -> None:
    """The table that remembers a person's decision about a pool recipe.

    Keyed on ``recipe_id`` and portal-owned, so a rejection survives the weekly
    pool refetch. Dismissing a recipe is permanent until reversed, not until
    next Monday — and a recipe that reappears in AH's popular listing must not
    quietly come back after someone has said no to it.

    Only rejections live here. Keeping a recipe *adopts* it, which is one
    action rather than two and puts it on the same footing as anything else the
    person chose: exempt from eviction by construction, not by a second flag
    that could disagree with the first.
    """
    with _engine.begin() as conn:
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS public.ah_recipe_verdicts (
                recipe_id   BIGINT PRIMARY KEY,
                verdict     TEXT NOT NULL CHECK (verdict IN ('rejected')),
                decided_at  TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        )


def reject_recipe(_engine, recipe_id: int) -> None:
    """Never show this recipe again, until the person says otherwise."""
    ensure_verdict_table(_engine)
    with _engine.begin() as conn:
        conn.execute(
            text("""
            INSERT INTO public.ah_recipe_verdicts (recipe_id, verdict)
            VALUES (CAST(:rid AS bigint), 'rejected')
            ON CONFLICT (recipe_id) DO UPDATE
                SET verdict = 'rejected', decided_at = now()
        """),
            {"rid": int(recipe_id)},
        )
    read_recipe_opportunity.clear()


def reinstate_recipe(_engine, recipe_id: int) -> None:
    """Undo a rejection, so a dismissal is not a trap."""
    ensure_verdict_table(_engine)
    with _engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM public.ah_recipe_verdicts "
                "WHERE recipe_id = CAST(:rid AS bigint)"
            ),
            {"rid": int(recipe_id)},
        )
    read_recipe_opportunity.clear()


@st.cache_data(ttl=_CACHE_TTL_S)
def read_rejected_recipes(_engine) -> pd.DataFrame:
    """What has been dismissed, so it can be reviewed and reversed.

    Joined to the pool rather than to dim_recipe: a rejected recipe is excluded
    from dim_recipe by design, so reading its name from there would return
    nothing and the list would look empty rather than populated.
    """
    ensure_verdict_table(_engine)
    sql = text("""
        SELECT
            v.recipe_id,
            COALESCE(p.title, 'Recept ' || v.recipe_id::text) AS recipe_name,
            p.image_url,
            p.rating_average,
            p.rating_count,
            v.decided_at
        FROM public.ah_recipe_verdicts AS v
        LEFT JOIN public."ah__pool_recipes" AS p ON v.recipe_id = p.recipe_id
        WHERE v.verdict = 'rejected'
        ORDER BY v.decided_at DESC
    """)
    try:
        with _engine.begin() as conn:
            return pd.read_sql_query(sql, conn)
    except Exception:
        # The pool table does not exist until the first refresh has run.
        empty: dict[str, list] = {
            "recipe_id": [],
            "recipe_name": [],
            "image_url": [],
            "rating_average": [],
            "rating_count": [],
            "decided_at": [],
        }
        return pd.DataFrame(empty)


# How long each scheduled job may go without succeeding before its silence is
# worth reporting. Derived from its own cadence rather than one global number:
# an hourly scrape two hours quiet is a problem, a weekly pool refresh two
# hours "late" is not.
#
# The heartbeat is listed at 36 hours - two missed cycles against the 24h
# access-token cap the twice-daily schedule was sized for.
_JOB_TOLERANCE_HOURS: dict[str, tuple[float, str]] = {
    "markdowns_refresh": (3, "de laatste kans-koopjes"),
    "daily_refresh": (30, "de bonusfolder en de receptprijzen"),
    "token_heartbeat": (36, "de AH-inlog"),
    "recipe_pool_refresh": (8 * 24, "de receptenlijst"),
    "source_freshness": (30, "de versheidscontrole"),
}

# Recovery needs an interactive browser login behind hCaptcha, which is the one
# thing here that cannot be done unattended - and it has expired twice already.
CREDENTIAL_JOB = "token_heartbeat"


@st.cache_data(ttl=_CACHE_TTL_S)
def read_pipeline_health(_engine) -> pd.DataFrame:
    """Which scheduled jobs have stopped succeeding, and for how long.

    Read from Dagster's own run table, which lives in this same Postgres. That
    is a deliberate coupling to Dagster's schema: the alternative is its
    GraphQL API, a second network dependency that fails exactly when something
    is already broken.

    "No successful run since" is a fact about *absence*, which is why this
    exists. Every event-driven path - the failure sensor, ntfy - can only
    report things that happened. A run that was never launched, a sensor whose
    tick threw, a schedule that stopped evaluating: none of those emit
    anything, and all of them leave the answers on screen quietly frozen.
    """
    sql = text("""
        SELECT
            pipeline_name AS job_name,
            MAX(create_timestamp) FILTER (WHERE status = 'SUCCESS') AS last_success,
            COUNT(*) FILTER (
                WHERE status = 'FAILURE'
                  AND create_timestamp > now() - interval '24 hours'
            ) AS failures_today
        FROM runs
        WHERE pipeline_name = ANY(:jobs)
        GROUP BY pipeline_name
    """)
    try:
        with _engine.begin() as conn:
            df = pd.read_sql_query(
                sql, conn, params={"jobs": list(_JOB_TOLERANCE_HOURS)}
            )
    except Exception:
        # Fail soft. A schema change on a Dagster upgrade, or a database that
        # cannot be read, degrades this page to what it did before this existed
        # rather than replacing an answer with an error.
        return pd.DataFrame(
            {"job_name": [], "last_success": [], "failures_today": [], "overdue_h": []}
        )

    known = set(df["job_name"]) if not df.empty else set()
    # A job that has never run at all is missing from the table entirely, which
    # is exactly the state worth reporting after a fresh deployment.
    missing = [j for j in _JOB_TOLERANCE_HOURS if j not in known]
    if missing:
        df = pd.concat(
            [
                df,
                pd.DataFrame(
                    {
                        "job_name": missing,
                        "last_success": [pd.NaT] * len(missing),
                        "failures_today": [0] * len(missing),
                    }
                ),
            ],
            ignore_index=True,
        )

    now = pd.Timestamp.now(tz="UTC")
    last = pd.to_datetime(df["last_success"], utc=True, errors="coerce")
    df["last_success"] = last
    df["overdue_h"] = (now - last).dt.total_seconds() / 3600
    df["tolerance_h"] = df["job_name"].map(lambda j: _JOB_TOLERANCE_HOURS[j][0])
    df["what"] = df["job_name"].map(lambda j: _JOB_TOLERANCE_HOURS[j][1])
    # NaT overdue means never succeeded, which is overdue by definition.
    df["is_overdue"] = df["overdue_h"].isna() | (df["overdue_h"] > df["tolerance_h"])
    return df.sort_values("job_name").reset_index(drop=True)


_LINKED_FOR_RECHECK = """
    SELECT p.concept_id,
           MIN(i.concept_name) AS concept_name,
           p.product_link,
           p.product_name,
           p.confirmed_at IS NOT NULL AS confirmed
    FROM public.ah_ingredient_products AS p
    JOIN public.ah__pool_recipe_ingredients AS i ON i.concept_id = p.concept_id
    WHERE i.concept_name IS NOT NULL
    GROUP BY p.concept_id, p.product_link, p.product_name, p.confirmed_at
"""


def read_linked_products(engine) -> list[dict]:
    """Every ingredient-to-product link, with the ingredient's name.

    The name is needed because whether a link is wrong depends on what was
    asked for: Verstegen Dille is the right answer to "gedroogde dille" and the
    wrong one to "verse dille".
    """
    with engine.begin() as conn:
        rows = conn.execute(text(_LINKED_FOR_RECHECK)).mappings().all()
    return [dict(r) for r in rows]


def withdraw_proposals(engine, links: list[tuple[int, str]]) -> int:
    """Remove unconfirmed proposals, by (concept_id, product_link).

    Refuses to touch a confirmed row even if asked. The guard is in the SQL
    rather than the caller because this is the one operation here that destroys
    a person's work if it is wrong, and a caller that forgets is likelier than
    a WHERE clause that changes.
    """
    if not links:
        return 0
    removed = 0
    with engine.begin() as conn:
        for concept_id, product_link in links:
            result = conn.execute(
                text(
                    "DELETE FROM public.ah_ingredient_products "
                    "WHERE concept_id = :cid AND product_link = :link "
                    "AND confirmed_at IS NULL"
                ),
                {"cid": int(concept_id), "link": product_link},
            )
            removed += result.rowcount or 0
    return removed


def flag_concepts(engine, flags: list[tuple[int, str]]) -> int:
    """Record that a concept's products contradict what they are.

    Re-flagging refreshes the reason and the timestamp: the contradiction may
    have changed since it was last raised, and a stale reason shown to a
    person is worse than none.
    """
    if not flags:
        return 0
    with engine.begin() as conn:
        for concept_id, reason in flags:
            conn.execute(
                text(
                    "INSERT INTO public.ah_ingredient_flags "
                    "(concept_id, reason) VALUES (:cid, :reason) "
                    "ON CONFLICT (concept_id) DO UPDATE SET "
                    "reason = EXCLUDED.reason, flagged_at = now()"
                ),
                {"cid": int(concept_id), "reason": reason[:500]},
            )
    return len(flags)


def clear_flag(engine, concept_id: int) -> None:
    """A person has dealt with it. Called when a resolution is confirmed."""
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM public.ah_ingredient_flags WHERE concept_id = :cid"),
            {"cid": int(concept_id)},
        )


def read_flag_reasons(engine) -> dict[int, str]:
    """Why each flagged concept was raised, for showing next to it."""
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT concept_id, reason FROM public.ah_ingredient_flags")
        ).all()
    return {int(r[0]): r[1] for r in rows}


def count_flagged_concepts(engine) -> int:
    """How many concepts are linked to something that contradicts them.

    Zero when the table does not exist yet: the portal must render on a
    database the resolution asset has never run against, and a missing table
    is "nothing flagged", not an error page.
    """
    try:
        with engine.begin() as conn:
            return int(
                conn.execute(
                    text("SELECT COUNT(*) FROM public.ah_ingredient_flags")
                ).scalar()
                or 0
            )
    except Exception:
        return 0


_STALE_CONCEPTS = """
    SELECT p.concept_id,
           MIN(i.concept_name) AS concept_name,
           COUNT(DISTINCT i.recipe_id) AS uses
    FROM public.ah_ingredient_products AS p
    JOIN public."ah__pool_recipe_ingredients" AS i ON i.concept_id = p.concept_id
    WHERE i.concept_name IS NOT NULL
    GROUP BY p.concept_id
    -- Nothing a person confirmed. Their decision is the answer, and
    -- re-proposing over it would be this system overruling them.
    HAVING BOOL_AND(p.confirmed_at IS NULL)
    -- Least recently proposed first, so successive runs cycle through the
    -- whole catalogue instead of re-examining the same head of the list.
    ORDER BY MIN(p.proposed_at) ASC, uses DESC
    LIMIT :limit
"""


def read_stale_concepts(engine, limit: int) -> list[dict]:
    """Concepts whose products were proposed by an older matcher.

    These never come up again on their own: the query that drives proposing
    skips any concept that already has a row, so a wrong answer recorded once
    stays recorded. That is where the known-bad matches actually are -
    "mierikswortel in pot" is linked to peanut butter, mint gum and two jars
    of pesto, and none of them contradicts the ingredient in a way the
    classification rules can see.
    """
    with engine.begin() as conn:
        rows = (
            conn.execute(text(_STALE_CONCEPTS), {"limit": int(limit)}).mappings().all()
        )
    return [dict(r) for r in rows]


def replace_proposals(engine, concept_id: int, products: list[dict]) -> int:
    """Swap a concept's unconfirmed proposals for a fresh set.

    Replaces rather than adds. The old proposals came from a matcher that
    compared names only; keeping them alongside a better answer would leave
    the wrong products available to win on price, which is exactly how a jar
    of pesto comes to decide the cost of a dish containing horseradish.

    Confirmed rows are left alone - the DELETE says so, rather than the
    caller having to remember.
    """
    if not products:
        return 0
    with engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM public.ah_ingredient_products "
                "WHERE concept_id = :cid AND confirmed_at IS NULL"
            ),
            {"cid": int(concept_id)},
        )
        for product in products:
            conn.execute(
                text(
                    "INSERT INTO public.ah_ingredient_products "
                    "(concept_id, product_link, product_name) "
                    "VALUES (:cid, :link, :name) "
                    "ON CONFLICT (concept_id, product_link) DO NOTHING"
                ),
                {
                    "cid": int(concept_id),
                    "link": product["product_link"],
                    "name": product["product_name"],
                },
            )
    return len(products)
