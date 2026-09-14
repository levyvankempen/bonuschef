## Why

Everything needed for the question this project exists to answer is now in place and none of it is being asked. Clearance is scraped hourly with prices, stock and expiry dates. The bonus feed is live and date-filtered. Recipes can be adopted from a catalogue of 24,803, their ingredients carry a stable concept id, and those concepts resolve to purchasable products. What is missing is the sentence that uses all of it: *tonight, cook this, because these ingredients just got cheap.*

Today a person opens Laatste kans, reads 120 discounted items, and does the join in their head against recipes they half-remember. That is the work the warehouse exists to do.

There is one hard constraint that shapes everything. **Albert Heijn cannot be asked which recipes use a given ingredient.** The `ingredients` parameter on recipe search is fuzzy OR-relevance, not a filter — searching two ingredients returns their union, and "rode kool" returns recipes containing no red cabbage — and none of the catalogue's facet groups is an ingredient. So the match must be computed here, against recipes whose ingredients we hold. We hold them only for recipes that have been adopted, and fetching all 24,803 is one request each.

## What Changes

- A page that answers what to cook tonight: recipes ranked by how much cheaper they are today than usual, with the discounted ingredients named and the reason for urgency shown.
- Discounts from both sources are considered — store clearance and the live bonus feed — and where both apply to an ingredient, the cheaper one counts.
- The ranking is honest about what it does not know: a recipe whose ingredients are not all priced is not presented as a bargain, and a saving is never claimed against a reference price too old to mean anything.
- Clearance urgency reaches the answer: an ingredient that expires today or has two left is why you go now rather than later, and that is the deciding fact at 17:30.
- The catalogue is drawn on within a bounded cost, so that a person who has adopted three recipes still gets suggestions, without the system attempting to hold all of Allerhande.

## Capabilities

### New Capabilities
- `recipe-opportunity`: what it means for a recipe to be a good idea today — how a saving is established, which recipes are eligible to be considered, and what must be withheld when the evidence is incomplete or stale.

### Modified Capabilities
- `portal`: adds the surface that answers the question, including what it shows when there is nothing worth cooking and when the data is not current.

## Impact

- New warehouse models joining recipes to clearance and to live bonus, at a grain that keeps store-scoped, hours-perishable prices out of the comparable cost series.
- `src/bonuschef/portal/` — a new page, which becomes the app's default destination.
- Possibly a scheduled job to widen the pool of recipes considered, within a stated request budget.
- No change to adoption, to resolution, or to how clearance and bonus are collected.
