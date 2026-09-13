## Context

See `proposal.md` — Why. Everything below is measured against the live database on 2026-09-13.

- `ah__bonus_products`: 1,362 rows, `loaded_at` 2026-07-06, **941 rows carry a `2999-12-31` sentinel end date**. `fct_bonus_price_comparison`: 214 rows, **199 expired**.
- `int_product_latest_price` is a **view** doing `GROUP BY` + self-join over 1.19M rows: 1.7s cold, and its `EXPLAIN` shows the CTE spilled to disk and scanned twice (~520 MB temp I/O per execution). Eight consumers — four tests and four models — so ~7s of a 17.5s build.
- 8,465 of 24,638 products have a latest observation from 2025-11.
- 696 `webshop_id`s map to >1 `product_link`; the `DISTINCT ON ... ORDER BY webshop_id, product_link` tie-break is alphabetical and picks the staler row in 340 cases.
- The `webshop_id` derivation is inlined in three marts, two of them without the `NULLIF` guard the third has.
- `public_marts` has **zero indexes**; `fct_products` is 1.19M rows / 157 MB, fully rebuilt every run from a strictly append-only weekly source.
- Clearance match rate is **88 of 119 (74%)**. The 31 misses have zero rows in `github__products` across all 66 snapshots — a source-coverage limit, not a join defect. An earlier claim of "1 of 121" was a hardcoded literal in a test fixture, not production data.

## Goals / Non-Goals

**Goals:**

- Stop publishing claims the data does not support.
- Make one reconciliation of products between sources, used everywhere.
- Make a stale input loud instead of invisible.
- Remove the avoidable ~6s of build work and the portal's sequential scans.

**Non-Goals:**

- Raising the clearance match rate above ~75%. That needs name- or concept-based matching, which is a separate change and a prerequisite for the recipe-opportunity work, not for correctness.
- Building `fct_recipe_opportunity`. It depends on the crosswalk this change extracts and on live bonus semantics; it is the next change, not this one.
- Re-keying `dim_product` on `webshop_id`. It is the right long-term shape and would dissolve the crosswalk problem entirely, but it touches every consumer including the portal, and doing it in the same change as the correctness fixes would make both unreviewable.

## Decisions

**The bonus filter lives in the mart, not in staging.**
`stg_ah__bonus_products` currently filters `WHERE is_bonus = true`, which is a business rule in a staging model and destroys the "this promotion has ended" signal at the earliest layer. Staging keeps every row; the marts decide what counts as live. That also means a future model can answer "what *was* on offer last month", which is impossible once the rows are gone.

**The sentinel is rejected by an upper bound, not by equality.**
941 rows end `2999-12-31`. Testing `bonus_end_date >= current_date` passes all of them, so the filter needs `AND bonus_end_date < '2100-01-01'`. Matching the literal `2999-12-31` would break the day AH picks a different sentinel; an upper bound is the assertion we actually mean — *this is not a real campaign end date*.

**Price staleness withholds the measure rather than flagging it.**
`dim_product` gains `price_observed_at` and `price_age_days`, and `real_savings_vs_tracked` becomes `NULL` beyond a threshold. Returning a number plus a warning flag would leave every consumer free to ignore the flag, and the portal already has four places that would have to. A `NULL` cannot be misread. The threshold is **45 days**: the GitHub snapshot source loads weekly, so 45 days is six missed loads — long enough not to fire on ordinary gaps, short enough to exclude the 2025-11 cohort entirely.

**One `int_product_crosswalk`, materialized as a table.**
It replaces three inlined copies whose behaviour already differs (two lack the `NULLIF` guard and will raise `invalid input syntax for type integer: ""` the first time a slug has no digits). Tie-break becomes `ORDER BY webshop_id, price_observed_at DESC NULLS LAST, product_link` — recency first, with the alphabetical fallback retained only to keep the result deterministic. This is also the prerequisite the recipe-opportunity change needs.

**`int_product_latest_price` becomes a table and a `DISTINCT ON`.**
Table because eight consumers re-derive it from 1.19M rows each. `DISTINCT ON` because it measured 1,105 ms against 1,702 ms for the `GROUP BY` + self-join, and avoids the temp spill. There is one semantic difference: the self-join returns every row tied on the maximum timestamp, `DISTINCT ON` returns one. There are zero ties today and the existing `unique` test catches any regression — so the risk is bounded by a test that already exists.

**`fct_products` becomes incremental with `delete+insert`.**
The source is append-only and loads weekly in fixed 16,173-row snapshots, so a full 157 MB rebuild every run is waste. `delete+insert` on `(product_link, snapshot_timestamp)` rather than `append` so a re-run of the same snapshot is idempotent — dlt can replay a load, and an `append` strategy would double the rows.

**Indexes are declared on the models, not applied by hand.**
`dbt_project.yml`'s `indexes` config, so they are recreated on every rebuild and live in version control. Without them the portal sequentially scans 157 MB per chart render.

**`on-run-start` stops creating the two dlt-owned tables.**
`ah__bonus_products` and `ah__store_markdowns` are dlt's. The live tables carry `_dlt_load_id` and `_dlt_id` columns and a unique constraint that the dbt DDL does not create, so on a fresh host whichever runs first wins and dlt then has to migrate the schema it thought it owned. Two owners for one table is the defect; dbt gives up its claim. The three portal-owned tables stay for now — they are genuinely dbt-adjacent and moving them is a separate argument.

**Tests are added where absence is currently load-bearing, not everywhere.**
The suite is 56 `not_null` and 7 `unique`. Rather than doubling it, this change adds: a `relationships` test from recipe ingredients to the catalogue at `severity: warn` (an ingredient with a typo'd link silently vanishes from its recipe today — but one bad hand-typed entry must not break the build); composite-grain uniqueness on the six untested marts; source freshness on all three sources; and the handful of business invariants whose violation would reach the UI as a wrong number or a raw enum code.

## Risks / Trade-offs

- **The portal will show far fewer products as "on bonus", and a user could read that as a regression.** → It is a correction: 199 of 214 were expired. Worth stating in the README, because the number will drop visibly and the cause will not be obvious later.
- **`real_savings_vs_tracked` becomes NULL for a subset of clearance items.** The portal's "Matched to tracked" metric will fall. → That metric is being cut by the portal redesign anyway; the honest count was never the point, and a saving computed against a 2025 price was worse than no saving.
- **Incremental models drift if the source is ever back-filled.** A late-arriving snapshot older than the current maximum would be skipped by the `WHERE snapshot_timestamp >` predicate. → The GitHub source is append-only by construction (one snapshot per commit, timestamped by commit). A `dbt run --full-refresh` is the escape hatch, and is worth naming in the README.
- **`dbt_utils` becomes a dependency**, so builds now need `dbt deps`. → CI already runs `dbt deps` in the `lint_sql` session, and the Dockerfile runs it at build time. No new step.
- **Withholding stale savings hides a number the user might still want.** → They can still see the reference price and its age; only the *derived claim* is withheld. A saving is an assertion about comparability, and that is exactly what is missing.

## Migration Plan

1. `dbt deps` then `dbt build --full-refresh` once, because `fct_products` changes materialization and `int_product_latest_price` changes from view to table. A plain `dbt build` would leave the old view in place.
2. The incremental model is seeded by that same full refresh; subsequent runs are incremental automatically.
3. Rollback is `git revert` plus another `--full-refresh`. No data is destroyed — every model is derived from `ah__*` and `github__*` source tables, which this change does not touch.

## Open Questions

- Whether the 45-day staleness threshold is right cannot be settled from one observation; the 2025-11 cohort is unambiguous but the boundary is not. It does not affect the specs or the task breakdown — only a constant.
