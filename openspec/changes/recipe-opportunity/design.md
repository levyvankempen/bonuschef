# Design

## Context

Four reviews informed this design: an architect, a UX designer, a data modeller, and a feasibility study that ran ~420 live requests against AH. Two of them overturned assumptions in the original proposal, and the record of that matters more than the conclusions.

**What was measured, not assumed:**

| Claim in the original proposal | Measurement | Effect |
|---|---|---|
| "fetching all 24,803 is one request each" | `recipe(id:)` alias-batches at 200/request; 7,555 recipes in 38 requests, 67s | wrong by 124×; the crawl is nearly free |
| A bounded pool is the interesting decision | 7,555-recipe pool yields **57 rankable recipes** under the original eligibility rule | pool size was never the constraint; resolution is |
| Every ingredient must be priced to rank | matcher resolves 34% of 10,919 concepts; 8.78 ingredients/recipe | 0.8% of the pool survives; the rule is fatal |
| Clearance and bonus rarely overlap | **2 products** are on both today | the fan-out is real, not hypothetical |
| `bonus_price` is a price you can pay | **146 of 256** live matched promotions are multibuy | the ranking would systematically overstate |

**The state the feature would ship into, verified against the live warehouse on 2026-09-14:** 23 products across 3 recipes, **0 on clearance**, **0 on bonus**. Clearance history holds 3 distinct days. This is not an argument against building it; it is the reason the degraded states below are specified as carefully as the happy path, and the reason the portal must show pool size against rankable count.

## Goals / Non-Goals

**Goals**
- Rank recipes by observed saving, resting on partial knowledge where necessary, without ever publishing a total the evidence does not support.
- Keep store-scoped, hours-perishable clearance out of the comparable cost history structurally rather than by filter.
- Make every reason a recipe is absent from the ranking reachable.
- Hold the catalogue within a request budget that clearance always outranks.

**Non-Goals**
- Unit conversion. Pack-size parsing across 24k `salesUnitSize` strings stays deferred; this change *discloses* the overstatement instead of fixing it.
- Re-keying `dim_product` on `webshop_id`. Named as a risk below, not undertaken here.
- Reverse lookup from clearance items to recipes. Measured and rejected — see below.
- Any change to adoption, resolution, or collection of clearance and bonus.

## Decisions

### 1. Rank on saving, withhold the total

**The original rule was wrong, and the way it was wrong is instructive.** It said a recipe may be ranked only when every ingredient resolves to a priced product. That conflates two different questions:

- *What does this recipe cost?* — genuinely unanswerable with an unpriced ingredient. A partial sum is not a total, and `fct_recipe_cost_latest` already withholds it. Unchanged.
- *How much cheaper is it today?* — a **difference**, and an ingredient that contributes nothing to the difference cannot change it. "At least €3.40 cheaper today" is completely true for a recipe with four unpriced ingredients.

The rule also collided with the proposal's own bounded-pool requirement: at 34% first-pass resolution and 8.78 ingredients per recipe, a freshly crawled 9-ingredient recipe has roughly a **0.1%** chance of full auto-resolution. Requiring both was incoherent.

So: `saving_total` is a **lower bound** and gates ranking; `cost_ordinary` / `cost_today` are published only for a fully priced basket, exactly as today. The portal renders the two differently and never lets one be read as the other.

### 2. One table for the ranking and the exclusions

`fct_recipe_opportunity` holds **every** recipe in the pool at every store. `opportunity_rank` is NULL for the unranked; `exclusion_reason` says why.

Two tables would mean two definitions of "eligible" that can drift, and "records are not dropped silently" would hold only by convention. One table makes it structural: there is no filter to forget, and `COUNT(*)` is the honest pool size — which is also what the portal must show. A narrow surface is a view over this, not a second computation.

`exclusion_reason`, most-fundamental first: `no_ingredients`, `no_priced_ingredient`, `no_discount_today`, or NULL for ranked.

### 3. Clearance is kept out of the cost history by dependency shape

`store_id` is manufactured in exactly one model (`int_store`) and introduced by exactly one `CROSS JOIN`, in `int_recipe_item_opportunity`. Nothing upstream knows a store exists. `int_recipe_items_priced`, `fct_recipe_cost_latest`, `fct_recipe_cost_history` and the breakdown marts are untouched and keep their `recipe_id`-only grain, so clearance is *structurally unable* to reach them.

```
int_recipe_items_priced ──┬─> fct_recipe_cost_latest   (grain: recipe_id)   ← no store, no clearance
                          └─> int_recipe_item_opportunity ← int_product_offer_today ← fct_store_clearance
                                     ▲
                                int_store  (manufactures store_id, once)
```

A test asserts exactly one model cross-joins the spine and that no cost model mentions clearance — so the next person to reach for it fails the suite rather than the review.

### 4. Where each fan-out dies

Six explosions; five collapse, and the sixth is disclosed rather than hidden.

| Explosion | Collapsed where | Why it cannot double-count |
|---|---|---|
| one `webshop_id` ↔ many `product_link` | `int_product_crosswalk`, `DISTINCT ON (webshop_id)` | already tested unique |
| one `product_link` ↔ many `webshop_id` | never happens | `webshop_id = regex(product_link)` is a *function*, so `product_link` is unique by construction — a theorem, not an observation |
| one product on clearance **and** bonus | `int_product_offer_today`, `DISTINCT ON (store_id, product_link)` | 192 offer rows → 190, exactly the 2 overlapping products |
| one concept → many products | `int_recipe_item_opportunity`, `DISTINCT ON (store_id, recipe_id, item_key)` | grain test |
| one recipe → many ingredients | `GROUP BY store_id, recipe_id` over a tested grain | cannot double-count over a proven grain |
| one item → many stores | `store_id` is *in* the grain | no aggregate crosses stores |

**The sixth: two ingredient lines resolving to the same product.** `_recipes_models.yml` already documents "ui" and "rode ui" both confirmed against a generic onion pack. Two lines are two shopping decisions, so the grain is right — but one clearance unit with stock 1 would be claimed twice. No uniqueness test can see it. A window function carries `lines_claiming_offer_product` to the item row and a `severity: warn` test asserts `stock >= lines_claiming_offer_product`. Zero violations today, because nothing is on clearance; the test exists for the day something is.

### 5. Multibuy is excluded from the saving

`bonus_price` on `1 + 1 gratis` is a per-unit price **conditional on buying two**. A recipe needing one unit does not get it. **57% of live matched promotions are multibuy**, which makes this a larger source of overstatement than the staleness problem the spec was already careful about.

`requires_multibuy` is derived from `bonus_mechanism`, and such offers are excluded from `saving_total` and reported as `conditional_saving` with the condition stated. This is a deliberate departure from the original spec's unqualified "the cheaper of the two counts".

### 6. Stale clearance withdraws one source; it does not blank the page

Clearance is store-scoped and perishable within the day. Promotions are national and week-scoped. Treating them identically was a category error: at 09:00 the day after a scrape, the bonus evidence is entirely sound and you still want dinner.

So the mart publishes **both** `saving_total` / `cost_today` and `saving_bonus_only` / `cost_today_bonus_only`, and the portal chooses at read time. This redundancy is load-bearing: `CURRENT_DATE` in a dbt model is evaluated **at build time**, so a model that filtered stale clearance away would grow more confidently wrong the longer it went unbuilt. The one correct place for a predicate whose truth changes at midnight with no pipeline running is the reader.

`saving_bonus_only` is recomputed from each item's best *promotional* offer, not derived by subtracting a clearance component — an item whose best offer was clearance must fall back to its bonus price, not to zero.

### 7. Crawl the whole catalogue; spend the effort on resolution

Measured: alias batching caps on a **GraphQL lexer token budget (~9,000 tokens/document)**, not an alias count — 238 aliases with the full field set, 500 with `id + modifiedAt`. Operating point **200**, deliberately below the ceiling, because the limit scales with fields-per-alias and adding one field would silently break a 238 batch.

`recipeSearch` pagination caps hard at `start + size ≤ 2000`, so the catalogue cannot be walked directly. It is enumerated by facet sweep — `allerhande-magazine` has 299 values summing to 14,956, none over the cap — then fetched in 200-alias batches.

| target | search reqs | fetch reqs | wall | bytes |
|---|---|---|---|---|
| 24,803 (full) | ~600–800 | 124 | ~8 min | 38 MB |
| steady state | 0 | ~51/day | seconds | — |

`modifiedAt` is present on 7,555/7,555 recipes and only **0.77%** changed in 30 days, so the steady state is an `id + modifiedAt` sweep at 500 aliases (50 requests) plus a re-fetch of the ~6 recipes/day that moved.

**This is why pool size is not the interesting decision.** Crawling all 24,803 today yields roughly 165 rankable recipes. Confirming concepts by hand — which costs **zero AH requests**, `matching.py` is entirely local at 24ms/concept — is what moves the number:

| confirmed concepts | rankable of 7,555 | mean ingredient coverage |
|---|---|---|
| 0 (today) | 57 (0.8%) | 44.5% |
| 500 | 1,233 (16.3%) | 76.2% |
| 1,500 | 3,238 (42.9%) | 85.7% |

Top 100 concepts cover 43% of all ingredient lines; top 1,000 cover 75.5%. The portal therefore points at the review queue ordered by pool frequency — that is the feature's real engine, and decision 1 is what lets partial coverage produce answers in the meantime.

### 8. Rejected: reverse lookup from clearance to recipes

Measured on 40 real clearance titles, top-10 candidates, fetched and verified:

| arm | precision @10 | items with zero usable hit |
|---|---|---|
| raw clearance title | 23.2% | 55% |
| hand-normalised term | 58.6% | 28% |

Both are **upper bounds** — the verifier accepted any token match, so "Elitehaver **ongezouten**" scored against "**ongezouten** roomboter". Three structural problems, none fixable by tuning: `ingredients:` is confirmed fuzzy (`ingredients:["spitskool"]` → 267 results, `searchText` → 270, identical top 5); today's clearance is **57% bakery and confectionery**, which are not recipe ingredients; and it must run hourly, ~1,300 requests/day, ~25× the incremental sweep — landing on the same unresolved concepts, so the recipes it finds are mostly unrankable anyway.

## Risks / Trade-offs

**Pack sizes overstate savings, and this change does not fix it.** A recipe calling for 100g of a 500g pack is costed — and *saved* — at the whole pack. A €2.00 clearance on a €4.99 pack reads as €2.00 saved on the meal. This biases the ranking toward recipes containing expensive large-pack ingredients, which is precisely the wrong bias for "what do I cook tonight". Mitigation is disclosure only: `units` and `sales_unit_size` are published and the portal says *hele verpakking*, never an unqualified *bespaard*. The real fix is the deferred unit work.

**`dim_product` is keyed on `product_link`, and every join here rests on the regex theorem.** The day AH changes slug format, four models break as a silent *reduction* in matches — which no uniqueness test catches. Re-keying on `webshop_id` dissolves it and remains a non-goal.

**A spec/code conflict is inherited.** `stg_ah__bonus_products` keeps rows carrying the `2999-12-31` sentinel (902 of 1,351 live), while the archived `price-intelligence` spec says a far-future end date shall not be treated as indefinite. The model is right — these are real standing offers, as the live bonus count demonstrated — so the spec needs amending to say a sentinel must be *distinguishable*, which `bonus_is_ongoing` already makes it. Settle it before building on top.

**The crawl must never be what discovers a dead credential.** It runs at ~04:00, after the 03:30 heartbeat has already proven the credential and outside the 11:00–20:00 clearance window. It aborts on the first auth rejection that survives one forced refresh, persists progress, and resumes the next day — a crawl retry-looping through the auth fallback chain is exactly how a refresh credential gets burned. `max_concurrent_runs: 1` serialises everything, so a long crawl holding the only slot would delay a clearance scrape; clearance is unbackfillable and therefore has absolute priority.

**`group_name="dlt"` is load-bearing.** `daily_refresh_job` selects `assets("ah__bonus_products") | (AssetSelection.all() - AssetSelection.groups("dlt"))`. A recipe asset outside that group would re-crawl the entire catalogue every night at 17:30, inside the dbt rebuild.

**The feature ships into its own empty state.** With 0 of 23 products discounted and 3 days of clearance history, the first thing rendered is "niets in de aanbieding". The degraded states are therefore not edge cases — they are the initial experience, and are specified and tested as first-class.
