## 1. The AH recipe client

- [x] 1.1 Split `graphql()` in `src/bonuschef/utils/ah_auth.py` into a transport (`_post_graphql`, returns the whole body) and the existing raising wrapper, plus a `graphql_partial()` that hands errors back; factor the 401/403 forced-refresh retry into one helper so it is not written twice. Verify `test_ah_auth.py` passes unchanged — the markdowns path must keep identical semantics
- [x] 1.2 Create `src/bonuschef/utils/ah_recipes.py` with `RecipeHit`, `Recipe`, `Ingredient` dataclasses and `AHRecipeUnavailable` / `AHRecipeNotFound` / `AHRecipeShapeError`; read the unit from `quantityUnit { singular plural }` rather than parsing it out of `text`, because a field cannot break silently and a text invariant can
- [x] 1.3 Implement `fetch_recipe(id)` carrying a canary recipe in the same document — AH answers an unknown id and a dead subgraph identically, so canary-null means unavailable and canary-present-with-target-null means not found; verify tests cover both plus HTTP 5xx
- [x] 1.4 Implement `search_recipes(text, size, start)` clamping size to 100, because AH silently returns 10 above that rather than erroring; verify a test asserts the clamp is applied to the outgoing variables
- [x] 1.5 Validate at the boundary in `_parse_recipe` — refuse an empty ingredient list, a missing concept id, a non-positive quantity or servings — so a shape change fails before anything is written rather than surfacing later as a wrong cost; verify a parametrised test covers each broken shape
- [x] 1.6 Pace requests at no more than 4/second and return `SearchPage(total=0, hits=())` for no results rather than raising; verify a test asserts an empty result is a value and not an exception

## 2. Storage

- [x] 2.1 Add portal-owned tables in `src/bonuschef/portal/db.py`'s existing `ensure_*` path: `ah_recipes` (keyed on AH's id, with the raw payload retained against AH changing shape), `ah_recipe_ingredients` (`quantity NUMERIC`, because 1½ is 1.5, with unit and the verbatim text), `ah_ingredient_products` (concept↔product, many-to-many, with a confirmed-at distinguishing a proposal from a decision), and `ah_ingredient_aliases`; verify a test asserts the schema and that dbt creates none of them
- [x] 2.2 Make adoption idempotent with `ON CONFLICT (recipe_id) DO NOTHING` so adopting the same recipe twice is a database guarantee rather than a UI check; verify a test asserts the second adoption adds nothing
- [x] 2.3 Split the write into a pure row builder and a thin executor so the interesting half is testable without a database; verify a test asserts the rows carry concept identity, name, quantity and unit

## 3. Matching

- [x] 3.1 Add `src/bonuschef/portal/matching.py` proposing products from `dim_product` by whole-word match, ranked by how few extra words the product name adds — "AH Courgette" beats "AH Courgettesoep" — with no network call at all; verify tests cover a clean match, a compound-only match that must be refused, and a no-match
- [x] 3.2 Attach the whole head group rather than a single winner, since several products satisfy one ingredient and which is cheapest changes daily; verify a test asserts multiple products attach for one concept
- [x] 3.3 Record proposals as unconfirmed and never overwrite a user decision, so re-running the matcher cannot silently revert a correction; verify a test asserts an upsert leaves a confirmed row alone

## 4. Warehouse

- [x] 4.1 Add staging models for the four new tables, keeping them thin; verify `dbt parse` succeeds and grain tests pass
- [x] 4.2 Converge both paths in `int_recipe_items_resolved`: a hand-entered ingredient is the degenerate case of a concept ingredient already resolved to exactly one product. Below this model nothing should know which path a recipe came from; verify a test asserts both kinds produce the same shape
- [x] 4.3 Change `int_recipe_items_priced` from `INNER JOIN` to a left join taking the cheapest attached product, so an unresolved ingredient survives into the mart instead of vanishing and making the recipe look cheaper; verify a test asserts an unresolved ingredient is still counted
- [x] 4.4 Make `fct_recipe_cost_latest` withhold `total_cost` when any item is unpriced and publish `items_total`, `items_priced` and `price_coverage`, matching what `fct_recipe_cost_history` already does; verify a test asserts a partial basket never publishes a total. **Note `portal/db.py` reads `total_cost` directly** — it must handle NULL in the same commit
- [x] 4.5 Add grain and referential tests for the new models; verify `dbt build` passes with no new failures

## 5. Portal

- [x] 5.1 Mount `dagster_home` into the `streamlit` service and set `AH_TOKEN_FILE`, without which the portal bootstraps its own token file and rotates the refresh credential out from under the daemon — the exact disuse expiry the heartbeat exists to prevent; verify a test asserts the mount and the variable
- [x] 5.2 Add a `recipes_rebuild` asset job over the existing recipe models and register it, so the portal can finish its own work; verify `test_definitions.py` covers it and that it adds no new asset the daily refresh would sweep up
- [x] 5.3 Replace `recipe_builder.py` with a catalogue flow: search on submit only — never per keystroke, which would be a third-party call during every rerun — then preview with ingredients and servings visible, then one adopt button. Verify tests cover found, nothing-found, unreachable and unreadable as four distinct outcomes
- [x] 5.4 Move the existing hand-entry flow to its own module behind an expander, keeping it working, and replace its `st.code("dbt run")` ending with the same build trigger; verify the existing add-recipe tests still pass and that no page instructs the user to run a command
- [x] 5.5 Make adopting non-blocking: the recipe exists the moment it is written, costing is observable and arrives later. Blocking for up to 180s per recipe would make adding twenty a half-hour vigil, which is the `dbt run` failure with better typography; verify a test asserts the page does not wait on the run
- [x] 5.6 Unresolved ingredients show as a count after adopting, and never block it. **The optional review dialog is deferred** — correcting a match still means editing the resolution table directly. The spec's confirm/correct requirement is therefore only partly met and stays open for the resolution change
- [x] 5.7 State on the recipe view that costing uses one product per ingredient, so a number is not read as more precise than it is; verify a test asserts the wording appears

## 6. Language

- [x] 6.1 Sweep the portal to one language. The `portal` capability requires it and the current pages violate it — the navigation says "Recepten" while the page says "Recipes", and "Laatste kans koopjes" sits above "No clearance items in the latest snapshot." Verify a test asserts no English user-facing strings remain in the page modules

## 7. Gate

- [x] 7.1 Run `uv run pytest` and confirm the suite passes with no new skips and no network access
- [x] 7.2 Run `uv run ty check src tests noxfile.py`, clean
- [x] 7.3 Run `uv run ruff check` and `ruff format --diff`, both clean
- [x] 7.4 Run `uv run sqlfluff lint` over the models, clean
- [x] 7.5 Rebuild the stack and adopt a real recipe end to end, confirming it appears with a cost and that an unresolved ingredient is visible
