# Tasks

## 1. Settle the inherited spec conflict

- [x] 1.1 Amend the archived `price-intelligence` spec so a far-future end date must be *distinguishable* rather than excluded, matching what `stg_ah__bonus_products` actually does and what the live data showed (902 of 1,351 rows carry the sentinel and are real standing offers)
- [x] 1.2 Add a test asserting `bonus_is_ongoing` is what distinguishes them, so the next reader does not re-litigate it from the model comment

## 2. The offer layer

- [x] 2.1 `int_store.sql` — the store spine, grain `store_id`, carrying `clearance_scraped_at` and `clearance_is_current`. The only model that manufactures `store_id`
- [x] 2.2 `int_product_offer_today.sql` — grain `(store_id, product_link)`, clearance and bonus unioned then collapsed by `DISTINCT ON` on cheapest price, tie-break to `bonus` (a week-long promotion beats one unit of clearance at equal price)
- [x] 2.3 Derive `requires_multibuy` from `bonus_mechanism` in the same model; assert against the 146 live multibuy rows that the regex catches `1 + 1 gratis`, `2 voor`, `2e halve prijs`
- [x] 2.4 Grain test on `(store_id, product_link)`; test that an offer is never dearer than the price it claims to discount; test that only clearance carries stock and expiry — if a bonus row ever arrives with stock, the urgency filter in task 4 is silently wrong
- [ ] 2.5 Verify the collapse on live data: 192 offer rows in, 190 out, the two overlapping products named

## 3. The candidate set

- [x] 3.1 `int_recipe_item_candidates.sql` — grain `(recipe_id, item_key, product_link)`, deliberately *not* unique on `(recipe_id, item_key)`. Without it, only the product that was cheapest *ordinarily* can carry a discount, and a clearance on a sibling of the same concept is invisible — which is the entire value of `ah_ingredient_products` being many-to-many
- [x] 3.2 Match its `valid_to IS NULL` filter to `int_recipe_items_priced` exactly, and add the singular test that proves the two describe the same basket

## 4. The opportunity grain

- [x] 4.1 `int_recipe_item_opportunity.sql` — grain `(store_id, recipe_id, item_key)`, the only `CROSS JOIN int_store` in the project
- [x] 4.2 Read the ordinary side from `int_recipe_items_priced`, never recompute it, so this mart and `fct_recipe_cost_latest` cannot disagree about what a recipe ordinarily costs
- [x] 4.3 Gate on reference-price age: `LEAST(price_ordinary, offer_price)` when comparable, else `price_ordinary`. `LEAST`, not the offer — a sibling candidate on clearance can still be dearer than the product ordinarily bought
- [x] 4.4 Exclude multibuy offers from `item_saving`; publish `item_conditional_saving` alongside with its condition
- [x] 4.5 Compute `item_saving_bonus_only` from each item's best *promotional* offer independently, not by subtracting a clearance component
- [x] 4.6 Publish `offer_withheld_stale_reference` so a discarded discount has an answer rather than silence
- [x] 4.7 Carry `lines_claiming_offer_product` by window function over `(store_id, recipe_id, offer_product_link)`
- [x] 4.8 Publish `units` and `sales_unit_size` for the pack-size disclosure
- [x] 4.9 Grain test; the saving-never-against-a-stale-price test; `price_today <= price_ordinary`; `item_saving >= 0`; `item_saving_bonus_only <= item_saving`; an unpriced ingredient is neither discounted nor comparable

## 5. The marts

- [x] 5.1 `fct_recipe_opportunity.sql` — grain `(store_id, recipe_id)`, **every** recipe in the pool keeps a row
- [x] 5.2 Rank on `saving_total > 0` with at least one priced ingredient — not on full costability (design decision 1). `opportunity_rank` NULL otherwise
- [x] 5.3 `exclusion_reason` in `no_ingredients` / `no_priced_ingredient` / `no_discount_today` / NULL, with a test that it is non-null exactly when `opportunity_rank` is null, so the two cannot drift
- [x] 5.4 Withhold `cost_ordinary` / `cost_today` unless `items_priced = items_total`; publish `saving_is_lower_bound` when it is not
- [x] 5.5 Urgency aggregates `FILTER (WHERE is_discounted AND offer_kind = 'clearance')` — a bonus line has no stock or expiry, and an unfiltered `MIN` would let a NULL-carrying bonus row read as "no urgency"
- [x] 5.6 Publish `clearance_items_stock_unknown` and `clearance_items_expiry_unknown` beside the `MIN`s: `MIN` skips NULLs, so all-unknown stock would otherwise be indistinguishable from no clearance at all, which reads as plenty
- [x] 5.7 `fct_recipe_opportunity_items.sql` — full grain, not filtered to discounted lines: an excluded recipe needs its unresolved line visible, and "the rest of the basket did not move" is itself an answer
- [x] 5.8 Singular test that `cost_ordinary` and `items_total` agree with `fct_recipe_cost_latest` — catches candidate-set drift, the concept fan-out double-count, and any divergence that would show two different answers to "what does this cost"
- [x] 5.9 Singular test that every discount comes from a product that can actually satisfy the ingredient
- [x] 5.10 `severity: warn` test that clearance stock covers the lines claiming it
- [x] 5.11 Python test that exactly one model cross-joins the store spine and no cost model references clearance or the offer layer

## 6. The pool of well-rated recipes

- [x] 6.1 Add `rating { average count }` to `_RECIPE_QUERY` in `ah_recipes.py`, with a test pinning that `rating` needs a subfield selection — a scalar selection fails validation, which is how the field was found
- [x] 6.2 Enumerate the pool with `recipeSearch(sortBy: POPULAR)`, `size: 100`, to the hard `start + size <= 2000` ceiling: 20 requests. Pin the ceiling in a test, since exceeding it returns `Subgraph errors redacted` rather than an error that names the cause
- [x] 6.3 Do not use `TRENDING` — it returned results identical to `NEWEST` and is not a popularity signal. Record that in the code, not only here
- [x] 6.4 Fetch the 2,000 in 200-alias batches: 10 requests. Keep 200 rather than the measured 238 ceiling, which is a document token budget and shrinks as fields are added — `rating` has just added some
- [x] 6.5 dlt source `ah__recipes` / `ah__recipe_ingredients`, `write_disposition="merge"`, `primary_key="recipe_id"`, storing `rating_average`, `rating_count`, `modified_at` and `fetched_at`
- [x] 6.6 `group_name="dlt"`, verified by a test against `daily_refresh_job`'s selection — outside that group the pool refetches nightly inside the 17:30 rebuild
- [x] 6.7 Weekly schedule at ~04:00 — after the 03:30 heartbeat has proven the credential, outside the 11:00–20:00 clearance window. 30 requests a week against a measured tolerance of ~420/day
- [x] 6.8 Evict pool recipes that fall out of the listing, **except** any that were adopted, entered by hand, or kept. A test must prove an adopted recipe survives a refresh that no longer returns it
- [x] 6.9 Abort on the first auth rejection surviving one forced refresh; never retry-loop through the auth fallback chain. At 30 requests there is nothing to resume, so the job simply fails and alerts
- [x] 6.10 Tests: enumeration stops at the ceiling, batch size pinned with its reason, eviction spares the exempt, schedule hour pinned

## 6b. Keeping and rejecting

- [x] 6b.1 Portal-owned table for a person's verdict on a recipe — kept or rejected — keyed on `recipe_id` so it survives the recipe being refetched
- [x] 6b.2 A rejected recipe is excluded from the ranking at the mart boundary, and its `exclusion_reason` says it was rejected rather than leaving it absent without record
- [x] 6b.3 Keeping a recipe adopts it, so it joins the person's own and becomes exempt from eviction — one action, not two
- [x] 6b.4 Tests: a rejection survives a refetch, a kept recipe survives an eviction sweep, reinstating clears the rejection, and a rejected recipe never reaches the ranking

## 7. The page

- [x] 7.1 `tonight_page.py` — the lead recipe in full with its responsible ingredients named, the rest listed briefly below
- [x] 7.2 Lower-bound savings rendered so they cannot be read as exact; no total shown for a partially priced recipe
- [x] 7.3 Urgency: stock and expiry from clearance lines only; never state a bound when stock is unknown
- [x] 7.4 Pack disclosure — *hele verpakking*, never an unqualified *bespaard*
- [x] 7.5 Multibuy shown separately with its condition, outside the ranked figure
- [x] 7.6 Stale clearance withdraws the source: re-rank on `saving_bonus_only`, strip clearance prices from ingredient cards, say clearance was set aside. Decided at **read** time from `clearance_scraped_at`, never at build time
- [x] 7.7 Five degraded states, each tested: nothing discounted, nothing adopted, clearance stale, bonus feed stale, warehouse unreachable
- [x] 7.8 Pool size against rankable count, with the reason a recipe is unranked reachable
- [x] 7.9 Keep and reject on every recommended recipe; the rejected list reachable and every entry reversible
- [x] 7.10 Show `rating_average` with `rating_count` beside it — five stars from three votes is not five stars from three hundred
- [x] 7.11 Offer the ingredient review queue ordered by pool frequency as the next action — it costs zero AH requests and is what makes the pool rankable
- [x] 7.12 Lift the freshness helpers out of `clearance_page.py` into `freshness.py` and use them in both, so the two pages cannot disagree about what "current" means
- [x] 7.13 Make it the portal's default destination in `app.py`
- [x] 7.14 AppTest coverage for each state; Dutch throughout, which `test_portal_language.py` now enforces

## 8. Verification

- [x] 8.1 Full `dbt build` on the live warehouse; every new test green
- [x] 8.2 Inject a known clearance offer and confirm the arithmetic end to end, including a stale-reference ingredient being discarded and a clearance/bonus overlap counting once
- [x] 8.3 Confirm `fct_recipe_cost_latest` is byte-identical before and after — the cost history must not have moved
- [x] 8.4 **Done — and the state stopped being empty.** Before the matcher ran, the page's own empty branch was what it showed: 83 recipes now rank out of 911, so the live page reads as an answer. The empty path did not stop mattering and is covered by test (`nothing discounted` renders the plain statement plus the cheapest-to-make fallback rather than a blank page). Run the page against today's genuinely empty state and confirm it reads as an answer rather than a failure
- [x] 8.5 `ruff check`, `ruff format`, `ty check`, full pytest suite DB- and network-free

## 9. Curating the pool, and making it rankable

Added after the first live run: 908 recipes priced 3.3% of their ingredients and
ranked nothing, because nothing ran the matcher in bulk. Fetching recipes is the
cheap half; knowing what an ingredient can be bought as is what makes them
rankable.

- [x] 9.1 Curate by construction, not by approving recipes one at a time: main courses only (`menugang=hoofdgerecht`), from AH's own everyday-dinner tag (`momenten=wat-eten-we-vandaag`) sorted by rating, plus this year's and last year's magazine issues for currency. **908 distinct recipes in 19 search requests, 4.9s** — cheaper than the undifferentiated top 2,000 it replaces, and it keeps side dishes, desserts and unloved outliers out of the ranking entirely
- [x] 9.2 One search request per magazine issue, which is not optional: **values within a filter group intersect rather than union**. Two issues in one filter returns recipes in *both*, which is 0 — measured, and the opposite of what the argument shape suggests (`hoofdgerecht AND bijgerecht` is 13 recipes). Pinned in a test, because batching would silently empty the pool's recency half rather than fail
- [x] 9.3 `ah__ingredient_proposals`: run `matching.propose_for` across every unresolved pool concept, most-used first so an interrupted run has done the work that mattered. Local regex against `dim_product` — **zero AH requests**
- [x] 9.4 Proposals never overwrite a decision (`propose_products`' `WHERE confirmed_at IS NULL`), so re-running after a catalogue refresh cannot revert a correction
- [x] 9.5 The proposal step joins `recipe_pool_refresh` — a refreshed pool with no matches ranks nothing, so a job that fetched and stopped would report success having achieved nothing — and the nightly rebuild, since a product that appeared today may resolve an ingredient that failed yesterday
- [x] 9.6 Offer the review queue from Vanavond, with a test that the page cannot name the work without offering it
- [x] 9.7 Verified live: **561 of 1,926 concepts matched in 90s**, mean ingredient coverage **3.3% → 46.5%**, ranked recipes **0 → 83**
- [ ] 9.8 **Open question for the operator.** Proposals are written unconfirmed, but costing does not yet distinguish proposed from confirmed, so unreviewed matches drive real prices. Either mark such recipes on the page or exclude unconfirmed matches from ranking — a judgement about how far to trust the matcher
