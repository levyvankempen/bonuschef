## Why

Two recipes exist. The reason is that adding one takes roughly nine interactions per ingredient — search, read a table, find the same name again in a separate multiselect, add, wait for a rerun, scroll, set a quantity — and ends by telling the user to open a terminal and run `dbt run`. Nobody types a twentieth recipe through that.

Everything downstream is blocked by it. A mart that ranks "which of my recipes got cheap today" over two recipes is not a product, and the clearance and bonus data that now works properly has almost nothing to be useful *about*.

Albert Heijn already has the recipes. Verified against the live API on 2026-09-13: `recipe(id:)` and `recipeSearch(query:)` on the same GraphQL endpoint and member token the clearance scrape already uses, returning title, servings, and ingredients with quantities. Better than expected, **`ingredients.id` is a stable ingredient-concept id** — `courgette` is `1853` across every recipe that uses it — which is the ingredient-concept layer this project would otherwise have had to invent.

What AH does **not** give is a mapping from those concepts to purchasable products. Tested across 16 ingredients: the concept ids live in their own namespace and none resolves to the right product. The service that probably held that mapping, `appie-recipe-bff`, returns a DNS failure from inside AH's own gateway and is decommissioned.

So the matching problem does not disappear — but it changes from "match this user's free text against 24,000 products, per recipe" into "map a few hundred concepts to products, once, in AH's own vocabulary on both sides".

## What Changes

- A recipe can be added by finding it in Albert Heijn's catalogue rather than by typing it, carrying its ingredients, quantities and servings.
- Ingredients are stored against AH's concept identity, so work spent resolving a concept to products is done once and reused by every recipe that shares it.
- Resolving a concept to purchasable products is explicit and correctable: the system proposes, the person confirms, and a concept with no confident match is recorded as unresolved rather than guessed at or silently dropped.
- The portal stops instructing the user to run a build by hand.

Deliberately **not** in this change: importing Allerhande wholesale, recommending recipes the user has not chosen, and the opportunity ranking itself. This change exists to make the next one worth building.

## Capabilities

### New Capabilities
- `recipe-catalogue`: how recipes enter the system and how their ingredients acquire an identity that can be priced — including what happens when an ingredient cannot be resolved to anything purchasable.

### Modified Capabilities
- `portal`: adds requirements for finding and adding a recipe, and for the portal completing its own work rather than delegating a build step to the user.

## Impact

- New dlt source and Dagster asset for AH recipe retrieval; a new job the portal can trigger.
- `src/bonuschef/utils/` — an AH recipe client alongside the existing token manager.
- New warehouse models for recipes, ingredient concepts, and the concept-to-product resolution; existing recipe cost models gain a second way for ingredients to arrive.
- `src/bonuschef/portal/recipe_builder.py` — replaced rather than adjusted.
- The hand-maintained `public.recipes` and `public.recipe_ingredients` keep working; this adds a path, it does not remove one.
- **A dependency on an unofficial API that has already lost one backend.** The specification requires the failure to be visible rather than silent.
