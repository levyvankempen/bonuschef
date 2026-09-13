## Why

The warehouse currently publishes claims that are not true, and the portal presents them without qualification.

- **`fct_bonus_price_comparison` has no date filter at all.** 199 of its 214 rows are promotions that ended on 2026-07-12. `is_on_bonus` therefore means "appeared in a snapshot we happened to take in July", not "is on offer". The AH bonus feed itself has not loaded since 2026-07-06 — 69 days — and nothing anywhere reports that.
- **34% of products carry a "latest price" from 2025-11.** `int_product_latest_price` takes `MAX(snapshot_timestamp)` over all history, so a delisted product keeps its last-ever price forever. 8,465 of 24,638 products are in that state, and that price is what `is_inflated` compares against — so the project's central claim, that advertised savings are often fake, is partly measured against prices from a different year.
- **The product crosswalk picks the wrong row.** 696 `webshop_id`s map to more than one `product_link` because AH renames slugs, and the tie-break is alphabetical, so 340 of them resolve to the staler price.
- Several models lose data silently: a recipe whose ingredients all fail to price disappears from `fct_recipe_cost_latest` entirely rather than showing an unknown cost; `total_cost_observed` sums over a `LEFT JOIN` and presents a partial basket as a total.
- The 63 data tests are 56 `not_null` and 7 `unique`. There is no referential-integrity test, no business-invariant test, and no source freshness — which is why a 69-day-old feed went unnoticed.

Separately, the build does ~6 seconds of avoidable work per run and `public_marts` has **zero indexes**, so the portal sequentially scans a 157 MB table on every chart.

## What Changes

- Live-only bonus semantics: promotions are filtered to the current date, handling the `2999-12-31` sentinel that 941 rows carry.
- Price staleness becomes visible and load-bearing: `dim_product` carries when its price was observed, and savings measures are withheld rather than computed against a price too old to mean anything.
- One shared product crosswalk replaces three inlined, divergent copies of the `webshop_id ↔ product_link` derivation, and its tie-break prefers the most recently observed row.
- Source freshness is declared for all three sources, so a feed that stops loading is reported rather than silently serving old rows.
- Referential integrity, grain uniqueness and business invariants become tested.
- Silent data loss is removed: recipes no longer vanish when unpriceable, and a partial basket is no longer presented as a total.
- Performance: the latest-price model is materialized rather than re-derived eight times, the 1.19M-row fact becomes incremental, and the marts the portal reads gain indexes.

## Capabilities

### New Capabilities
- `price-intelligence`: what the warehouse asserts about prices, savings and promotions — when a comparison is meaningful, when a promotion counts as live, and what must be withheld rather than guessed.
- `data-quality`: the guarantees the warehouse makes about its own output — grain, referential integrity, source freshness, and the obligation to fail or warn rather than silently drop a record.

### Modified Capabilities
<!-- None. -->

## Impact

- `src/bonuschef/sql/models/` — new `int_product_crosswalk`; changes to `int_product_latest_price`, `dim_product`, `fct_products`, `fct_bonus_price_comparison`, `fct_store_clearance`, `fct_recipe_cost_latest`, `fct_recipe_cost_history`, `int_recipe_items_priced`, `stg_ah__bonus_products`.
- `src/bonuschef/sql/dbt_project.yml` — `on-run-start` stops creating two dlt-owned tables; materialization defaults.
- `src/bonuschef/sql/models/**/_*.yml` — freshness, relationships, grain and invariant tests; `packages.yml` for `dbt_utils`.
- `src/bonuschef/portal/` — the portal reads `real_savings_vs_tracked` and `is_on_bonus`, whose meaning changes; the clearance page's "Matched to tracked" metric is affected.
- `tests/unit/` — coverage for the SQL-adjacent Python and the dbt project config.
- **Behaviour visibly changes**: far fewer products will show as "on bonus", because most currently shown are not.
