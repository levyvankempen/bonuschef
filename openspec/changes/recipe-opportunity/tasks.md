# Tasks

## 1. Settle the inherited spec conflict

- [ ] 1.1 Amend the archived `price-intelligence` spec so a far-future end date must be *distinguishable* rather than excluded, matching what `stg_ah__bonus_products` actually does and what the live data showed (902 of 1,351 rows carry the sentinel and are real standing offers)
- [ ] 1.2 Add a test asserting `bonus_is_ongoing` is what distinguishes them, so the next reader does not re-litigate it from the model comment

## 2. The offer layer

- [ ] 2.1 `int_store.sql` — the store spine, grain `store_id`, carrying `clearance_scraped_at` and `clearance_is_current`. The only model that manufactures `store_id`
- [ ] 2.2 `int_product_offer_today.sql` — grain `(store_id, product_link)`, clearance and bonus unioned then collapsed by `DISTINCT ON` on cheapest price, tie-break to `bonus` (a week-long promotion beats one unit of clearance at equal price)
- [ ] 2.3 Derive `requires_multibuy` from `bonus_mechanism` in the same model; assert against the 146 live multibuy rows that the regex catches `1 + 1 gratis`, `2 voor`, `2e halve prijs`
- [ ] 2.4 Grain test on `(store_id, product_link)`; test that an offer is never dearer than the price it claims to discount; test that only clearance carries stock and expiry — if a bonus row ever arrives with stock, the urgency filter in task 4 is silently wrong
- [ ] 2.5 Verify the collapse on live data: 192 offer rows in, 190 out, the two overlapping products named

## 3. The candidate set

- [ ] 3.1 `int_recipe_item_candidates.sql` — grain `(recipe_id, item_key, product_link)`, deliberately *not* unique on `(recipe_id, item_key)`. Without it, only the product that was cheapest *ordinarily* can carry a discount, and a clearance on a sibling of the same concept is invisible — which is the entire value of `ah_ingredient_products` being many-to-many
- [ ] 3.2 Match its `valid_to IS NULL` filter to `int_recipe_items_priced` exactly, and add the singular test that proves the two describe the same basket

## 4. The opportunity grain

- [ ] 4.1 `int_recipe_item_opportunity.sql` — grain `(store_id, recipe_id, item_key)`, the only `CROSS JOIN int_store` in the project
- [ ] 4.2 Read the ordinary side from `int_recipe_items_priced`, never recompute it, so this mart and `fct_recipe_cost_latest` cannot disagree about what a recipe ordinarily costs
- [ ] 4.3 Gate on reference-price age: `LEAST(price_ordinary, offer_price)` when comparable, else `price_ordinary`. `LEAST`, not the offer — a sibling candidate on clearance can still be dearer than the product ordinarily bought
- [ ] 4.4 Exclude multibuy offers from `item_saving`; publish `item_conditional_saving` alongside with its condition
- [ ] 4.5 Compute `item_saving_bonus_only` from each item's best *promotional* offer independently, not by subtracting a clearance component
- [ ] 4.6 Publish `offer_withheld_stale_reference` so a discarded discount has an answer rather than silence
- [ ] 4.7 Carry `lines_claiming_offer_product` by window function over `(store_id, recipe_id, offer_product_link)`
- [ ] 4.8 Publish `units` and `sales_unit_size` for the pack-size disclosure
- [ ] 4.9 Grain test; the saving-never-against-a-stale-price test; `price_today <= price_ordinary`; `item_saving >= 0`; `item_saving_bonus_only <= item_saving`; an unpriced ingredient is neither discounted nor comparable

## 5. The marts

- [ ] 5.1 `fct_recipe_opportunity.sql` — grain `(store_id, recipe_id)`, **every** recipe in the pool keeps a row
- [ ] 5.2 Rank on `saving_total > 0` with at least one priced ingredient — not on full costability (design decision 1). `opportunity_rank` NULL otherwise
- [ ] 5.3 `exclusion_reason` in `no_ingredients` / `no_priced_ingredient` / `no_discount_today` / NULL, with a test that it is non-null exactly when `opportunity_rank` is null, so the two cannot drift
- [ ] 5.4 Withhold `cost_ordinary` / `cost_today` unless `items_priced = items_total`; publish `saving_is_lower_bound` when it is not
- [ ] 5.5 Urgency aggregates `FILTER (WHERE is_discounted AND offer_kind = 'clearance')` — a bonus line has no stock or expiry, and an unfiltered `MIN` would let a NULL-carrying bonus row read as "no urgency"
- [ ] 5.6 Publish `clearance_items_stock_unknown` and `clearance_items_expiry_unknown` beside the `MIN`s: `MIN` skips NULLs, so all-unknown stock would otherwise be indistinguishable from no clearance at all, which reads as plenty
- [ ] 5.7 `fct_recipe_opportunity_items.sql` — full grain, not filtered to discounted lines: an excluded recipe needs its unresolved line visible, and "the rest of the basket did not move" is itself an answer
- [ ] 5.8 Singular test that `cost_ordinary` and `items_total` agree with `fct_recipe_cost_latest` — catches candidate-set drift, the concept fan-out double-count, and any divergence that would show two different answers to "what does this cost"
- [ ] 5.9 Singular test that every discount comes from a product that can actually satisfy the ingredient
- [ ] 5.10 `severity: warn` test that clearance stock covers the lines claiming it
- [ ] 5.11 Python test that exactly one model cross-joins the store spine and no cost model references clearance or the offer layer

## 6. The catalogue pool

- [ ] 6.1 dlt source `ah__recipes` / `ah__recipe_ingredients`, `write_disposition="merge"`, `primary_key="recipe_id"` — a slowly-changing dimension, *not* the append-only clearance pattern where the curve is the data
- [ ] 6.2 `group_name="dlt"`, verified by a test against `daily_refresh_job`'s selection — outside that group the catalogue re-crawls nightly inside the 17:30 rebuild
- [ ] 6.3 Facet-sweep enumeration; `recipeSearch` caps at `start + size <= 2000`, so deep pagination is impossible and facets are the only route. Sweep `allerhande-magazine` first (299 values, 14,956 ids)
- [ ] 6.4 Alias-batched fetch at **200**, not the 238 ceiling — the limit is a document token budget, so one more field silently breaks a 238 batch
- [ ] 6.5 Store `modifiedAt` and `fetched_at`; incremental sweep at 500 aliases (`id + modifiedAt` only), re-fetching only what moved (~0.03%/day)
- [ ] 6.6 Own job and schedule at ~04:00 — after the 03:30 heartbeat has proven the credential, outside the 11:00–20:00 clearance window
- [ ] 6.7 Daily request budget with a hard cap of 500; abort the whole crawl on the first auth rejection surviving one forced refresh; persist progress and resume next day; never retry-loop through the auth fallback chain
- [ ] 6.8 Bound runtime well under the 3600s `run_monitoring` cap — `max_concurrent_runs: 1` means a long crawl holds the only slot
- [ ] 6.9 Tests: budget enforced, abort-on-rejection does not retry, resume picks up where it stopped, batch size and schedule hour pinned with the reasons above

## 7. The page

- [ ] 7.1 `tonight_page.py` — the lead recipe in full with its responsible ingredients named, the rest listed briefly below
- [ ] 7.2 Lower-bound savings rendered so they cannot be read as exact; no total shown for a partially priced recipe
- [ ] 7.3 Urgency: stock and expiry from clearance lines only; never state a bound when stock is unknown
- [ ] 7.4 Pack disclosure — *hele verpakking*, never an unqualified *bespaard*
- [ ] 7.5 Multibuy shown separately with its condition, outside the ranked figure
- [ ] 7.6 Stale clearance withdraws the source: re-rank on `saving_bonus_only`, strip clearance prices from ingredient cards, say clearance was set aside. Decided at **read** time from `clearance_scraped_at`, never at build time
- [ ] 7.7 Five degraded states, each tested: nothing discounted, nothing adopted, clearance stale, bonus feed stale, warehouse unreachable
- [ ] 7.8 Pool size against rankable count, with the reason a recipe is unranked reachable
- [ ] 7.9 Offer the ingredient review queue ordered by pool frequency as the next action — it is what turns 57 rankable into 1,233, and costs zero AH requests
- [ ] 7.10 Lift the freshness helpers out of `clearance_page.py` into `freshness.py` and use them in both, so the two pages cannot disagree about what "current" means
- [ ] 7.11 Make it the portal's default destination in `app.py`
- [ ] 7.12 AppTest coverage for each state; Dutch throughout, which `test_portal_language.py` now enforces

## 8. Verification

- [ ] 8.1 Full `dbt build` on the live warehouse; every new test green
- [ ] 8.2 Inject a known clearance offer and confirm the arithmetic end to end, including a stale-reference ingredient being discarded and a clearance/bonus overlap counting once
- [ ] 8.3 Confirm `fct_recipe_cost_latest` is byte-identical before and after — the cost history must not have moved
- [ ] 8.4 Run the page against today's genuinely empty state and confirm it reads as an answer rather than a failure
- [ ] 8.5 `ruff check`, `ruff format`, `ty check`, full pytest suite DB- and network-free
