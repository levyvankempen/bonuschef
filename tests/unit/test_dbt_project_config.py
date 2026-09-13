"""The dbt project's own configuration.

These guard decisions that are invisible in SQL but expensive to rediscover:
who owns which table, and which models must not silently revert to a view.
"""

from __future__ import annotations

from pathlib import Path

import yaml

SQL_DIR = Path(__file__).resolve().parents[2] / "src" / "bonuschef" / "sql"
PROJECT = SQL_DIR / "dbt_project.yml"
MODELS = SQL_DIR / "models"


def _project() -> dict:
    return yaml.safe_load(PROJECT.read_text())


def test_dbt_does_not_create_dlt_owned_tables():
    """dlt creates ah__bonus_products and ah__store_markdowns with _dlt_id and
    _dlt_load_id columns and a unique constraint. When dbt's on-run-start also
    created them, whichever ran first on a fresh host won and dlt then had to
    migrate a schema it thought it owned."""
    hooks = " ".join(_project().get("on-run-start", []))
    for table in ("ah__bonus_products", "ah__store_markdowns"):
        assert f"CREATE TABLE IF NOT EXISTS public.{table}" not in hooks, (
            f"dbt is creating {table}, which dlt owns"
        )


def test_price_comparability_threshold_is_configured():
    """A savings claim needs a reference price recent enough to be comparable;
    a third of the catalogue was last observed ten months ago."""
    max_age = _project()["vars"]["max_price_age_days"]
    assert isinstance(max_age, int)
    # Source loads weekly, so the threshold must survive ordinary gaps while
    # still excluding a previous season.
    assert 14 <= max_age <= 120


def test_the_expensive_models_are_not_views():
    """int_product_latest_price has eight consumers and derives from 1.19M rows;
    as a view each consumer re-derived it, spilling to disk twice."""
    sql = (MODELS / "intermediate/inventory/int_product_latest_price.sql").read_text()
    assert "materialized='table'" in sql

    facts = (MODELS / "marts/inventory/fct_products.sql").read_text()
    assert "materialized='incremental'" in facts
    # append would double the rows when dlt replays a load.
    assert "incremental_strategy='delete+insert'" in facts


def test_the_portal_joins_are_indexed():
    """public_marts had zero indexes, so the portal sequentially scanned a
    157 MB table on every chart."""
    for model, column in (
        ("marts/inventory/fct_products.sql", "product_link"),
        ("marts/inventory/dim_product.sql", "product_link"),
    ):
        sql = (MODELS / model).read_text()
        assert "indexes=[" in sql, f"{model} declares no index"
        assert column in sql


def test_promotions_are_filtered_to_the_present():
    """Promotions that ended are not offers."""
    sql = (MODELS / "marts/inventory/fct_bonus_price_comparison.sql").read_text()
    assert "bonus_start_date <= CURRENT_DATE" in sql
    assert "bonus_end_date >= CURRENT_DATE" in sql


def test_open_ended_offers_are_not_mistaken_for_stale_rows():
    """AH dates standing offers - "5% volume voordeel" and the like - as
    2999-12-31, meaning "no end date". An earlier version read that as a stale
    sentinel and rejected it with an upper bound, silently excluding every
    volume discount. A stale feed is caught by source freshness, not by
    second-guessing a date."""
    mart = (MODELS / "marts/inventory/fct_bonus_price_comparison.sql").read_text()
    assert "2100-01-01" not in mart, "an upper bound would drop open-ended offers"

    staging = (MODELS / "staging/ah/stg_ah__bonus_products.sql").read_text()
    # Consumers still get to tell a standing discount from a campaign ending
    # Sunday - they are different propositions.
    assert "bonus_is_ongoing" in staging


def test_the_product_crosswalk_exists_once():
    """The webshop_id derivation was inlined in three marts with three
    behaviours, two of them missing the NULLIF guard."""
    crosswalk = MODELS / "intermediate/inventory/int_product_crosswalk.sql"
    assert crosswalk.exists()
    assert "NULLIF" in crosswalk.read_text()
    # Recency, not alphabetical: the old tie-break picked the staler slug for
    # 340 of the 696 renamed products. Assert the ordering's meaning rather than
    # its formatting - sqlfluff normalises ASC/DESC keywords.
    order_by = crosswalk.read_text().split("ORDER BY")[1]
    assert order_by.index("price_observed_at DESC") < order_by.index("product_link"), (
        "the tie-break must prefer the most recent observation, not the slug"
    )

    for model in (
        "marts/inventory/fct_store_clearance.sql",
        "marts/inventory/fct_bonus_price_comparison.sql",
        "marts/recipes/fct_recipe_cost_breakdown_bonus.sql",
    ):
        sql = (MODELS / model).read_text()
        assert "REGEXP_REPLACE" not in sql, f"{model} still derives webshop_id itself"


def test_sources_declare_freshness():
    """A feed that stopped loading for 69 days went unreported."""
    for path in ("staging/ah/_ah__sources.yml", "staging/github/_github__sources.yml"):
        doc = yaml.safe_load((MODELS / path).read_text())
        for source in doc["sources"]:
            for table in source["tables"]:
                assert "freshness" in table, f"{table['name']} has no freshness"
                assert "loaded_at_field" in table
