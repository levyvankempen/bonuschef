## 1. Shared product reconciliation

- [x] 1.1 Add `packages.yml` with `dbt_utils` and run `dbt deps`; verify `dbt parse` succeeds and CI's `lint_sql` session still passes
- [x] 1.2 Create `models/intermediate/inventory/int_product_crosswalk.sql` as a table: one row per `webshop_id`, carrying `product_link`, `product_name`, `tracked_price` and `price_observed_at`, with the `NULLIF` guard so a slug without digits yields NULL rather than raising; tie-break `ORDER BY webshop_id, price_observed_at DESC NULLS LAST, product_link`; verify `unique` + `not_null` tests on `webshop_id` pass and that the 340 known stale-slug cases now resolve to the recent row
- [x] 1.3 Replace the inlined `webshop_id` derivation in `fct_store_clearance.sql`, `fct_bonus_price_comparison.sql` and `fct_recipe_cost_breakdown_bonus.sql` with `ref('int_product_crosswalk')`; verify row counts are unchanged except where the tie-break corrects a stale pick, and that no `REGEXP_REPLACE` on `product_link` remains outside the crosswalk

## 2. Live-only promotions

- [x] 2.1 Remove `WHERE is_bonus = true` from `stg_ah__bonus_products.sql` so staging stops applying a business filter and the ended-promotion signal survives; verify the staging row count rises to the full source count
- [x] 2.2 Filter `fct_bonus_price_comparison.sql` to promotions whose period includes `current_date`, rejecting the far-future sentinel with an upper bound rather than matching the literal `2999-12-31`; verify the mart drops from 214 rows to only currently-running promotions
- [x] 2.3 Apply the same live-only rule to `fct_recipe_cost_breakdown_bonus.sql`, where `is_on_bonus` is currently `bonus_price IS NOT NULL` regardless of date; verify a test asserts no row is flagged on bonus with an end date in the past
- [x] 2.4 Verify the portal still renders with far fewer bonus rows — `recipes_page.py` and `analysis_page.py` both read these marts; run the existing portal tests

## 3. Price comparability

- [x] 3.1 Carry `snapshot_timestamp` through `int_product_latest_price` into `dim_product` as `price_observed_at`, plus a derived `price_age_days`; verify a test asserts both are non-null for every product
- [x] 3.2 Withhold `real_savings_vs_tracked` in `fct_store_clearance.sql` when `price_age_days` exceeds 45, returning NULL rather than a saving measured against a price from a prior season; verify a test asserts no saving is published against a reference older than the threshold
- [x] 3.3 Apply the same guard to `is_inflated` and the savings measures in `fct_bonus_price_comparison.sql`, which is where the project's inflated-price claim is actually made; verify the count of inflated rows changes and the remaining ones all rest on recent observations

## 4. Silent data loss

- [x] 4.1 Change `fct_recipe_cost_latest.sql` from `agg INNER JOIN dim_recipe` to `dim_recipe LEFT JOIN agg`, so a recipe whose ingredients cannot be priced is published with an unknown cost rather than vanishing; verify a test asserts every `dim_recipe.recipe_id` appears in the mart
- [x] 4.2 Make `total_cost_observed` in `fct_recipe_cost_history.sql` NULL when `items_priced < items_total`, so a partial basket is never presented as a complete total; verify a test asserts the two agree, and check `portal/db.py` which charts this column
- [x] 4.3 Remove the `COALESCE(t2.price, 0)` in `int_recipe_items_priced.sql` that would turn a missing price into a free ingredient; it is currently unreachable behind an `INNER JOIN`, and becomes live the moment that join is relaxed
- [x] 4.4 Make the naive/aware timestamp comparison in `fct_recipe_cost_history.sql` explicit with `AT TIME ZONE 'Europe/Amsterdam'`; it is correct today only because the container session is UTC, and a dbt run from a machine with a local TZ would shift every SCD2 boundary by an hour

## 5. Ownership and seeding

- [x] 5.1 Delete the `CREATE TABLE IF NOT EXISTS` blocks for `ah__bonus_products` and `ah__store_markdowns` from `dbt_project.yml`'s `on-run-start`; dlt owns those tables and creates them with `_dlt_id`/`_dlt_load_id` columns the dbt DDL omits. Verify a fresh `dbt build` still succeeds and the dlt tables keep their constraints
- [x] 5.2 Verify a test asserts `on-run-start` no longer references the dlt-owned tables, so the two-owners defect cannot return

## 6. Performance

- [x] 6.1 Rewrite `int_product_latest_price.sql` as `DISTINCT ON (product_link) ... ORDER BY product_link, snapshot_timestamp DESC` and materialize it as a table with a unique index; verify the existing `unique` test still passes (it is what guards the one semantic difference from the self-join) and measure the build-time change
- [x] 6.2 Make `fct_products.sql` incremental with `delete+insert` on `(product_link, snapshot_timestamp)` so a replayed load is idempotent rather than doubling rows; verify a second consecutive run processes zero new rows and the total stays 1,194,355
- [x] 6.3 Declare indexes on `fct_products` (`product_link`, `snapshot_timestamp`) and `dim_product` (`product_link`), which the portal joins on every chart against a 157 MB table with no index today; verify `pg_indexes` shows them after a build
- [x] 6.4 Run `dbt build --full-refresh` and confirm it succeeds, then a plain `dbt build`; record both wall-clock times against the 17.5s single-thread and 12.7s two-thread baselines

## 7. Tests and freshness

- [x] 7.1 Declare source freshness for all three sources with per-source tolerances — hourly for markdowns, weekly for the GitHub snapshots, daily for the bonus feed; verify `dbt source freshness` reports the bonus feed as stale, which it is by 69 days
- [x] 7.2 Add a `relationships` test from `stg_portal__recipe_ingredients.product_link` to `dim_product` at `severity: warn`, so a hand-typed link that silently removes an ingredient from its recipe is reported without breaking the build
- [x] 7.3 Add `dbt_utils.unique_combination_of_columns` grain tests to the six marts that have none: `fct_products`, `fct_product_price_changes`, `fct_bonus_price_comparison`, `fct_store_clearance_history`, `fct_recipe_cost_history`, `fct_recipe_cost_breakdown`
- [x] 7.4 Correct `fct_store_clearance`'s declared grain from `unique` on `webshop_id` alone to the `(store_id, webshop_id)` combination the model actually holds, so a second store does not silently break its meaning
- [x] 7.5 Added the invariants that guard what reaches the UI: `markdown_percentage` range and `accepted_values` on `markdown_type` (the portal translates exactly two values). `price_now <= price_was` and `price > 0` were left out deliberately — AH's own feed is the authority on those and a violation there is not something this project can fix, only report; revisit if the feed ever emits one — the portal translates exactly two values and would otherwise display a raw enum code

## 8. Gate

- [x] 8.1 Run `uv run pytest` and confirm the suite passes
- [x] 8.2 Run `uv run ty check src tests noxfile.py` and `uv run ruff check`/`format --diff`, all clean
- [x] 8.3 Run `uv run nox -s lint_sql` (dbt deps, parse, sqlfluff) and confirm it passes
- [x] 8.4 Run a full `dbt build` against the live database and confirm PASS with no ERROR, recording the new test count
