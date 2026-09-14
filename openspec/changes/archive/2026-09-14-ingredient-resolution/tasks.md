## 1. Decision state

- [x] 1.1 Add `public.ah_ingredient_review` recording `resolved` or `none_exists` per concept, so "a person looked and there is nothing" is distinguishable from "nobody has looked" — the second cannot be expressed by a NULL on the products table; verify a test asserts the three states are distinct
- [x] 1.2 Add `confirm_resolution(engine, concept_id, product_links)` writing the person's choice: set `confirmed_at` on what they picked, delete what they did not, and record the review state; verify a test asserts a deselected product is removed and a chosen one is marked confirmed
- [x] 1.3 Add `mark_no_product(engine, concept_id)` for an ingredient with no purchasable equivalent; verify a test asserts it stops appearing as outstanding while the recipe's cost stays incomplete
- [x] 1.4 Verify the existing `propose_products` guard holds: a matcher run over a confirmed concept must change nothing, while an unreviewed one may still be filled. This is the durability guarantee and it lives in SQL rather than in a code path someone can forget

## 2. Reading what is outstanding

- [x] 2.1 Add `read_unresolved_concepts(engine, recipe_id=None)` returning concepts with no confirmed product and no review, optionally narrowed to one recipe; verify a test asserts a concept marked `none_exists` is excluded
- [x] 2.2 Add `read_concept_resolution(engine, concept_id)` returning the products currently attached and whether each was chosen or proposed; verify a test asserts the two are distinguishable
- [x] 2.3 Add a product search over `dim_product` for the case where the matcher proposed nothing usable, so a person can find the product themselves; verify a test asserts it is bounded

## 3. The review surface

- [x] 3.1 Add a dialog listing every outstanding ingredient together with its proposals pre-selected, settled by one button — not one step per ingredient, which is the failure the whole feature exists to undo; verify an `AppTest` case asserts several concepts appear in one dialog
- [x] 3.2 Make an empty selection a valid answer recorded as "nothing satisfies this", rather than a validation error; verify a test asserts submitting with nothing chosen succeeds and records the state
- [x] 3.3 Offer the review from the post-adoption card where the unresolved count already appears, without blocking adoption; verify a test asserts adopting still needs no resolution step
- [x] 3.4 Offer correction from the recipe view wherever a resolved product is shown, scoped to that one ingredient; verify a test asserts the control appears next to a resolved ingredient
- [x] 3.5 Trigger a cost rebuild after a change without blocking on it; verify a test asserts the rebuild is started and the dialog does not wait

## 4. The recipe view

- [x] 4.1 Show, per ingredient, which product it resolved to, or that it is unresolved, or that it was decided to have no purchasable equivalent — three states, visibly different; verify tests cover each
- [x] 4.2 Verify the recipe total stays withheld when any ingredient is unpriced, including one marked as having no product — unbuyable is not free

## 5. Gate

- [x] 5.1 `uv run pytest`, no new skips, no network
- [x] 5.2 `uv run ty check src tests noxfile.py`, clean
- [x] 5.3 `uv run ruff check` and `ruff format --diff`, clean
- [x] 5.4 `uv run sqlfluff lint` over the models, clean
- [x] 5.5 Resolve the five outstanding ingredients of the adopted recipe in the running portal and confirm its cost completes
