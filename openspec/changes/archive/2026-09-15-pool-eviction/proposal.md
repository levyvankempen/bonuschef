## Why

The pool asset's own docstring says it: *"the pool is refreshed whole rather than accumulated"*. It is not. Both resources load with `write_disposition="merge"`, which upserts and never deletes, and nothing downstream filters on `fetched_at`. A recipe that falls out of AH's popular listing stays in the pool and keeps being ranked, forever.

The binding requirement is explicit — *"recipes that have fallen out of favour leave it, and the total held stays within the stated bound"* — and the code does the opposite. Today it is invisible because the pool has only ever been loaded from one enumeration. It becomes visible the first time AH's listing turns over: the pool grows past 908, the honest count the portal is required to show starts overstating what is actually current, and the ingredient review queue lengthens with concepts belonging to recipes nobody would be offered any more.

It also quietly defeats the curation that was the whole point. A pool bounded by "AH's 908 best-rated current main courses" that never lets anything go is, after a year, "every main course AH has featured since last September".

## What Changes

- The pool holds what the latest enumeration returned, and nothing else.
- A person's own recipes are unaffected, as they already are: adopted, hand-entered and explicitly kept recipes are exempt from eviction by construction, because they do not live in the pool table.
- A rejection continues to outlive the refetch, since it is keyed on recipe id rather than on the pool row.

## Capabilities

### Modified Capabilities
- `recipe-opportunity`: the requirement that the pool is refreshed rather than accumulated is actually enforced.

## Impact

- `src/bonuschef/dags/defs/assets/dlt/ah_recipe_pool/` — how the two resources load.
- No change to what is ranked, to eviction exemptions, or to any saving.
