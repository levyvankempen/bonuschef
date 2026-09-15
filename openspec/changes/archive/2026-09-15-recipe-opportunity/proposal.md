## Why

Everything needed for the question this project exists to answer is now in place and none of it is being asked. Clearance is scraped hourly with prices, stock and expiry dates. The bonus feed is live and date-filtered. Recipes can be adopted from a catalogue of 24,803, their ingredients carry a stable concept id, and those concepts resolve to purchasable products. What is missing is the sentence that uses all of it: *tonight, cook this, because these ingredients just got cheap.*

Today a person opens Laatste kans, reads 120 discounted items, and does the join in their head against recipes they half-remember. That is the work the warehouse exists to do.

There is one hard constraint that shapes everything. **Albert Heijn cannot be asked which recipes use a given ingredient.** The `ingredients` parameter on recipe search is fuzzy OR-relevance, not a filter — searching two ingredients returns their union, and "rode kool" returns recipes containing no red cabbage — and none of the catalogue's facet groups is an ingredient. So the match must be computed here, against recipes whose ingredients we hold.

Holding them is cheap, which was not obvious. `recipe(id:)` alias-batches at 200 per request, so the entire 24,803-recipe catalogue is roughly 900 requests and eight minutes, once, and about 51 requests a day to keep current. That is less than a single afternoon of clearance scraping. The pool was never the expensive part.

The expensive part is resolution, and it is the whole problem. Against a measured 7,555-recipe pool holding 10,919 distinct ingredient concepts, the project's own matcher resolves 34% of them unaided. Requiring every ingredient of a recipe to be priced before it can be ranked leaves **57 rankable recipes out of 7,555** — under one percent. Confirming the 500 most frequent concepts by hand takes that to 1,233, and 1,500 concepts takes it to 3,238, because concept frequency is steep and every confirmation is reusable forever. So the ranking must be able to rest on partial knowledge, and the portal must point at the review queue that widens it.

## What Changes

- A page that answers what to cook tonight: recipes ranked by how much cheaper they are today than usual, with the discounted ingredients named and the reason for urgency shown.
- Discounts from both sources are considered — store clearance and the live bonus feed — and where both apply to an ingredient, the cheaper one counts.
- A saving may rest on partial knowledge and is then shown as a lower bound; a total cost is still withheld until every ingredient is priced. A saving is never claimed against a reference price too old to mean anything, nor against a promotion whose price requires buying more than the recipe needs.
- Clearance urgency reaches the answer: an ingredient that expires today or has two left is why you go now rather than later, and that is the deciding fact at 17:30.
- When clearance ages out, the page withdraws it as evidence and re-ranks on promotions alone rather than going blank — promotions are national and week-scoped, so they do not perish overnight the way clearance does.
- The catalogue is held in full, under a stated daily request budget that clearance collection always outranks, and the portal shows how many recipes it holds against how many it can presently rank.

## Capabilities

### New Capabilities
- `recipe-opportunity`: what it means for a recipe to be a good idea today — how a saving is established, which recipes are eligible to be considered, and what must be withheld when the evidence is incomplete or stale.

### Modified Capabilities
- `portal`: adds the surface that answers the question, including what it shows when there is nothing worth cooking and when the data is not current.

## Impact

- New warehouse models joining recipes to clearance and to live bonus, at a grain that keeps store-scoped, hours-perishable prices out of the comparable cost series. The existing cost models are untouched, and it is their dependency shape rather than a filter that keeps clearance out of them.
- `src/bonuschef/portal/` — a new page, which becomes the app's default destination.
- A new dlt source and its own scheduled job holding the recipe catalogue, outside the nightly rebuild.
- No change to adoption, to resolution, or to how clearance and bonus are collected.
- One conflict to settle first: `stg_ah__bonus_products` contradicts the archived `price-intelligence` spec on the far-future end-date sentinel. The model is right and the spec needs amending; this change inherits the disagreement either way.
