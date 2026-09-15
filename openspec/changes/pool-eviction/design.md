# Design

## Context

`write_disposition="merge"` upserts on the primary key and never deletes. That is right for a slowly-changing dimension you accumulate; it is wrong for a set you re-derive. The pool is the second kind: each refresh asks AH for its current best-rated main courses, and the answer is the whole truth about what the pool should contain.

Nothing downstream compensates. `stg_ah__pool_recipes` selects every row; `int_pool_recipes_available` filters only on adoption and rejection. So a recipe that dropped out of AH's listing three months ago is still ranked today.

## Decisions

### `replace`, not a `fetched_at` filter

Two ways to get eviction:

1. `write_disposition="replace"` — the load truncates and writes what it found.
2. Keep `merge`, and filter staging to `MAX(fetched_at)`.

**(1).** The second leaves every superseded row in the table forever, so the disk cost the requirement exists to bound is unbounded anyway — it just stops being visible in the mart. It also means every consumer must remember the filter, and the one that forgets reads a pool that silently includes three months of history. That is the same shape as the bug being fixed.

`replace` makes the table mean what its name says. The cost is that a failed load could leave the pool empty — which is why the asset already refuses to write when it has no recipes, raising rather than publishing an empty pool over a good one. That guard was written before this change and is what makes `replace` safe.

### The exemptions are untouched

Adopted, hand-entered and explicitly kept recipes are not in `ah__pool_recipes` at all — they live in the portal-owned tables. Truncating the pool cannot reach them, which is the property that makes this change small. Rejections are keyed on `recipe_id` in `ah_recipe_verdicts`, also portal-owned, so a rejected recipe that reappears in a later enumeration is still filtered out by `int_pool_recipes_available`.

## Risks / Trade-offs

**A partial enumeration silently shrinks the pool.** If AH returns 300 recipes instead of 908 — a facet gone missing, a filter quietly rejected — `replace` writes 300 and the rest are gone until the next refresh. `merge` would have hidden that by keeping the old rows.

I consider the visible version better: the portal already shows the pool size, so a collapse shows up as a number that dropped rather than as a ranking quietly drawn from stale recipes. The asset's existing "refusing to write an empty pool over a good one" guard covers the total failure; a partial one is reported by the count the page is required to display.
