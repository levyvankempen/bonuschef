## Context

See `proposal.md` — Why. Everything below is verified against AH's live API, not inferred.

**What the interface gives us** (`POST https://api.ah.nl/graphql`, member token — the same credential the clearance scrape uses):

- `recipe(id: Int!, servings: Int)` → `id title description href classifications courses cookTime ovenTime waitTime publishedAt modifiedAt servings{number type min max} images{url width height} tags{key value} preparation{steps} ingredients{id quantity quantityUnit{singular plural} text name{singular plural}}`
- `recipeSearch(query: RecipeSearchParams!)` where the params are `searchText`, `ingredients`, `size`, `start`, `filters`, `sortBy`. Result is `page{total}` and `result{id title slug courses images rating tags time}`.

**Traps found by probing, each of which would otherwise have been discovered in production:**

- `size` **caps at 100 and silently returns 10 above that** — no error.
- `recipe(id:)` answers an unknown id *identically* to a broken subgraph: HTTP 200, `data.recipe = null`, `"Subgraph errors redacted"`. The two are indistinguishable without help.
- Concept ids are stable across recipes but **not canonical**: of 467 sampled ingredient names, 6 carry two ids (`courgette` is both `1853` and `219282`).
- `quantity` is **fractional** — `1.5` for "1½ courgette". `public.recipe_ingredients.quantity` is `INTEGER NOT NULL`.
- No facet group in `RecipeSearchQueryFilter` is an ingredient, and the `ingredients` param is fuzzy OR-relevance (`"courgette zalm"` returns their union, 2057 results). **"What can I cook from today's clearance" cannot be asked of AH** and must be computed locally.

**What the existing code cannot do:** `public.recipe_ingredients` has `quantity INTEGER NOT NULL` and `product_link TEXT NOT NULL`. The first cannot hold 1.5; the second makes an unresolved ingredient structurally unrepresentable. New tables are forced, not preferred.

## Goals / Non-Goals

**Goals:**

- Get from two recipes to twenty in minutes rather than evenings.
- Store ingredient identity so resolving an ingredient is work done once for all recipes that share it.
- Keep the hand-entry path working, and keep every existing honesty guarantee.

**Non-Goals:**

- **Unit conversion.** Deferred deliberately and at some length below.
- Importing Allerhande wholesale, ranking recipes by opportunity, or asking AH which recipes use a clearance item — the last being impossible anyway.
- Re-fetching adopted recipes when AH edits them. `modifiedAt` exists and makes it easy later.

## Decisions

**Costing uses one product per ingredient, and the page says so.**
An AH recipe asks for `300 g quinoa`; the cost model multiplies `quantity × price` where quantity means *packs*. Feeding 300 in produces 300 packs of quinoa — a confident wrong number, which is exactly what the whole `dbt-model-integrity` change existed to stop. Bridging the two needs pack-size parsing across 24,000 `salesUnitSize` strings ("per stuk", "6 stuks", "500 g"), which is the largest piece of work in sight and none of it is the flow this change is about. So v1 costs one product per ingredient — precisely the fidelity hand entry has today — stores the recipe's own quantity and unit verbatim beside it, and states the limitation on the page rather than letting a plausible number imply precision it lacks. The ranking this unblocks is driven by *which* ingredients went on offer, and barely moves on quantity precision.

**`quantityUnit` is read from the API, not parsed out of text.**
`RecipeIngredient.quantityUnit { singular plural }` returns `g`, `el`, `tl`, `teen`, or empty for countable items. This matters because the obvious alternative — stripping the ingredient name and the leading number off `text` — rests on an invariant ("text always ends with the ingredient name") that holds today and would break silently the day AH changes its formatting. Reading a field cannot break silently; it breaks loudly.

**Every fetch carries a canary recipe in the same document.**
Because AH reports "no such recipe" and "the recipe subgraph is down" with byte-identical responses, and the specification requires those to be distinguishable. A second, known-good recipe id in the same query costs no extra round trip: canary null → unavailable, canary present and target null → not found. The one caveat is that AH could retire the canary id, which fails loudly rather than silently and is a one-line constant.

**The client lives in `utils/`, not as a dlt source or a Dagster asset.**
Three reasons, each sufficient. Search must answer in one round trip to a person typing, and a Dagster run launch is seconds of latency delivered as a run status rather than a readable error. Adoption is parameterised by recipe id, and assets are not parameterised per run — an adopting asset would also be swept into `daily_refresh` by `AssetSelection.all()` and re-adopt nightly. And dlt earns its keep for repeated snapshots of a whole feed; this is one row, once, chosen by a human.

**Auto-match at adopt time; confirmation is never a required step.**
If adopting nine ingredients requires confirming nine matches, this is the old builder in a warmer palette and the user stops at recipe two. The matcher runs locally against `dim_product` — no network — and writes its proposals. The asymmetry that makes this safe: a wrong auto-match costs "this recipe is €0.40 off until noticed", correctable in two taps from where it's visible; a mandatory confirmation step costs the entire change. Only concepts with **zero** candidates are surfaced, as a count with an optional review.

**The portal gets read access to the shared token file.**
`docker-compose.yml` currently gives `streamlit` no `dagster_home` mount, so `default_token_file()` would fall through to a path that does not exist and the portal would bootstrap its *own* token from `.env` — then rotate the refresh credential out from under the daemon, recreating the disuse-expiry failure `token_heartbeat_job` exists to prevent. Mounting the volume and setting `AH_TOKEN_FILE` fixes it with no code change. Concurrent access is safe because `TokenStore.save` writes a temp file and `os.replace`s it, so a reader sees old or new, never torn.

**An alias table for duplicate concepts.**
6 of 467 names carry two ids. Without aliasing, the spec's "resolving it once serves both" quietly fails for about one ingredient in seventy-eight, and the user resolves courgette twice wondering why. The table is two columns and starts empty.

**New portal-owned tables, and dbt does not create them.**
`dbt-model-integrity` removed dbt's DDL for dlt-owned tables because two owners for one schema is a defect. The same reasoning applies here: the portal owns these, dbt declares them as sources and creates nothing. A user's confirmed resolution survives `dbt run --full-refresh` precisely because dbt cannot touch it.

## Risks / Trade-offs

- **A second dependency on an unofficial API that has already lost one backend.** → Adoption materialises a complete local copy, including the raw payload, so adopted recipes keep working if `recipe(id:)` disappears tomorrow; only new adoptions stop, and hand entry remains. That is the mitigation, and it is structural rather than hopeful.
- **A wrong auto-match produces a plausible price.** → Bounded by being correctable in two taps wherever it shows, and by the fact that an unmatched ingredient is *visibly* unmatched rather than silently dropped. The alternative — mandatory confirmation — trades a small, correctable error for the failure of the whole change.
- **One product per ingredient means the absolute costs are wrong** for any recipe wanting 300 g of something sold in 500 g packs. → Stated on the page rather than implied away. Relative movement, which is what the next change ranks on, is preserved.
- **The portal now holds the member credential.** Interactive search shares a credential with the scheduled pipelines, so a throttle earned by clicking would cost the clearance scrape — the one append-only, unbackfillable stream in the project. → Paced at 4 req/s, search only on submit and never per keystroke, and no per-hit detail fetches.
- **Adopted recipes are user state with no load cadence**, so source freshness cannot meaningfully apply to them. → Declared as user-owned, like `public.recipes`.

## Migration Plan

1. Land the repo changes; the CI session set is the gate.
2. `docker compose up -d --build` — the portal gains the `dagster_home` mount, and the new tables are created by the portal's existing startup path.
3. Nothing to migrate. Existing hand-entered recipes are untouched and keep working through the same downstream models.
4. Rollback is `git revert` plus a rebuild. Adopted recipes would remain in their own tables, unread.

## Open Questions

- Whether duplicate concept ids need aliasing in practice, or whether the six observed are rare enough to ignore, can only be answered once twenty recipes exist. The table is created either way; populating it is a later decision and affects no other design choice.
