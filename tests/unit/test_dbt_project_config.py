"""The dbt project's own configuration.

These guard decisions that are invisible in SQL but expensive to rediscover:
who owns which table, and which models must not silently revert to a view.
"""

from __future__ import annotations

import re

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
    # The distinction is the whole reason keeping these rows is honest rather
    # than sloppy, and the price-intelligence spec now says so in those terms.
    # Without the flag, "not excluded" would just mean "not distinguished".
    assert "2100-01-01" in staging, (
        "the sentinel must still be recognised, only not dropped"
    )

    spec = (
        Path(__file__).resolve().parents[2]
        / "openspec"
        / "specs"
        / "price-intelligence"
        / "spec.md"
    )
    if spec.exists():
        text = spec.read_text()
        assert "SHALL be distinguishable" in text, (
            "the spec once said a sentinel SHALL NOT be treated as an indefinite "
            "promotion, which the model deliberately contradicts; if that wording "
            "returns, code and spec disagree again"
        )


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


def test_only_one_model_manufactures_a_store_scoped_recipe_row():
    """Clearance is store-scoped and perishable within the day, and the spec
    forbids it from entering the comparable cost history.

    That is enforced by dependency shape rather than by a filter someone can
    forget: exactly one model CROSS JOINs the store spine, and no cost model
    references clearance or the offer layer at all.
    """
    cross_joiners = sorted(
        p.name
        for p in MODELS.rglob("*.sql")
        if "int_store" in (text := p.read_text()) and "CROSS JOIN" in text.upper()
    )
    # Two models are entitled to a store, and only two. int_product_offer_today
    # needs one because a promotion is national and must be given a store before
    # it can be unioned with clearance; int_recipe_item_opportunity needs one
    # because it is the grain where recipes become store-scoped. A third would
    # mean some other part of the project had grown a store dimension.
    assert cross_joiners == [
        "int_product_offer_today.sql",
        "int_recipe_item_opportunity.sql",
    ], f"a third model reaching the store spine: {cross_joiners}"

    for name in (
        "marts/recipes/fct_recipe_cost_latest.sql",
        "marts/recipes/fct_recipe_cost_history.sql",
        "marts/recipes/fct_recipe_cost_breakdown.sql",
        "intermediate/recipes/int_recipe_items_priced.sql",
    ):
        sql = (MODELS / name).read_text()
        assert "fct_store_clearance" not in sql, f"{name} reaches clearance"
        assert "int_product_offer_today" not in sql, f"{name} reaches clearance"


def test_the_opportunity_gates_savings_on_price_age():
    sql = (MODELS / "intermediate/recipes/int_recipe_item_opportunity.sql").read_text()
    assert "var('max_price_age_days')" in sql
    # LEAST, not the offer price: a sibling candidate of the same concept can be
    # on clearance and still be dearer than the product we would ordinarily buy,
    # and a discount must never make an ingredient more expensive.
    assert "LEAST(price_ordinary, offer_price)" in sql


def test_multibuy_offers_are_kept_out_of_the_ranked_saving():
    """bonus_price on a "1 + 1 gratis" is the per-unit price you get only by
    buying two. A recipe needing one unit does not get it, and over half of live
    matched promotions are of this kind - a larger source of overstatement than
    the staleness rule the spec was already careful about."""
    offers = (MODELS / "intermediate/inventory/int_product_offer_today.sql").read_text()
    assert "requires_multibuy" in offers

    opportunity = (
        MODELS / "intermediate/recipes/int_recipe_item_opportunity.sql"
    ).read_text()
    # The chosen offer excludes them, and they are reported in their own column.
    assert "WHERE NOT o.requires_multibuy" in opportunity
    assert "item_conditional_saving" in opportunity


def test_the_opportunity_publishes_both_totals_for_read_time_degrading():
    """CURRENT_DATE in a dbt model is evaluated when the model is built, so a
    mart that filtered stale clearance away would grow more confidently wrong
    the longer it went unbuilt. The mart hands the portal both totals and the
    snapshot time; the portal decides. That redundancy is load-bearing."""
    mart = (MODELS / "marts/recipes/fct_recipe_opportunity.sql").read_text()
    for column in ("saving_total", "saving_bonus_only", "clearance_scraped_at"):
        assert column in mart, f"{column} is what lets the portal withdraw clearance"


def test_the_pool_stays_out_of_the_users_own_recipes():
    """dim_recipe means "the recipes this person has", and the cost history
    exists to track how *their* meals move in price.

    Folding a 2,000-recipe suggestion pool into it would put strangers' recipes
    on the Mijn recepten page and record 2,000 extra rows per snapshot in a
    history nobody asked for. The opportunity mart unions the two for itself.
    """
    dim = (MODELS / "marts/recipes/dim_recipe.sql").read_text()
    assert (
        "pool" not in dim.split("--")[0] or "int_pool_recipes_available" not in dim
    ), "dim_recipe must not read the pool"
    assert "stg_ah__pool_recipes" not in dim

    for name in (
        "marts/recipes/fct_recipe_cost_latest.sql",
        "marts/recipes/fct_recipe_cost_history.sql",
    ):
        sql = (MODELS / name).read_text()
        assert "int_pool_recipes_available" not in sql, f"{name} would cost the pool"
        assert "stg_ah__pool_recipes" not in sql, f"{name} would cost the pool"

    # And the opportunity mart does reach it, or nothing would be rankable.
    opportunity = (MODELS / "marts/recipes/fct_recipe_opportunity.sql").read_text()
    assert "int_pool_recipes_available" in opportunity


def test_a_rejected_recipe_cannot_reappear_after_a_refetch():
    """The pool is refetched whole every week. A rejection keyed on anything
    that the refetch rewrites would silently expire, and a recipe someone said
    no to would come back."""
    pool = (MODELS / "intermediate/recipes/int_pool_recipes_available.sql").read_text()
    assert "stg_portal__ah_recipe_verdicts" in pool
    # Adopted recipes are exempt from eviction for the same reason: the person
    # chose them, and that outranks AH's ordering.
    assert "stg_portal__ah_recipes" in pool


def test_every_published_saving_is_gated_on_price_age():
    """A saving measured against a price nobody has seen for months is not a
    saving, and this project publishes savings from three different models.

    fct_recipe_cost_breakdown_bonus recomputed its own from
    int_product_latest_price at any age, losing a guard that the row it was
    joined to had already applied - so Vanavond refused to count an offer while
    Recepten claimed EUR 0.70 for it on the same day. Every model that
    publishes a saving must either apply the age gate or take a figure from one
    that did.
    """
    publishers = {
        "marts/inventory/fct_bonus_price_comparison.sql",
        "marts/inventory/fct_store_clearance.sql",
        "marts/recipes/fct_recipe_cost_breakdown_bonus.sql",
        "intermediate/recipes/int_recipe_item_opportunity.sql",
    }
    for name in publishers:
        sql = (MODELS / name).read_text()
        gated = "max_price_age_days" in sql
        # ...or it inherits an already-gated figure rather than deriving one.
        inherits = "bp.real_savings" in sql or "cw.real_savings" in sql
        assert gated or inherits, (
            f"{name} publishes a saving without gating on price age, and does "
            "not take one from a model that did"
        )

    # And the models that must never see clearance still do not.
    for name in ("marts/recipes/fct_recipe_cost_latest.sql",):
        assert "fct_store_clearance" not in (MODELS / name).read_text()


def test_no_jinja_expression_has_been_given_a_table_alias():
    """sqlfluff's auto-fix once "qualified" a Jinja variable, turning
    `> {{ var('max_price_age_days') }}` into `> i.45` - valid-looking SQL that
    fails to compile.

    The python suite cannot catch this: it never compiles dbt. It surfaced only
    on a live build, as a Database Error in the very test that guards the
    project's most important invariant. Anything matching alias-dot-Jinja is
    almost certainly the same fixer doing the same thing.
    """
    offenders = []
    for folder in ("models", "tests"):
        root = MODELS.parent / folder
        if not root.exists():
            continue
        for path in root.rglob("*.sql"):
            for n, line in enumerate(path.read_text().splitlines(), 1):
                if re.search(r"[A-Za-z_][A-Za-z0-9_]*\.\{\{", line):
                    offenders.append(f"{path.name}:{n}: {line.strip()[:70]}")
    assert not offenders, "a table alias was attached to a Jinja expression:\n" + "\n".join(
        offenders
    )
