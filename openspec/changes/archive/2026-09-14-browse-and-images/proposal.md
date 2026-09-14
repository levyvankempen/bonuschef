## Why

Two gaps, both about recognising things rather than reading them.

**The clearance list has no pictures.** The card already renders one — the redesign made a point of using the image "already being queried and thrown away" — but every one of the 121 current rows has `image_url` NULL. The join goes through `product_images`, a table the portal scrapes one product at a time and which holds 14 rows, all recipe ingredients. Meanwhile AH returns the image on the clearance query itself: `bargainItems` exposes `imagePack`, which nothing asks for. A list read in a shop, where you are matching a name against a shelf, is exactly where a picture does the most work.

**Recipes can only be found by typing a search term.** You have to already know what you want. Allerhande is the part of AH people actually browse — what is new, what is in season — and adopting from it currently means guessing a word. The catalogue supports being browsed: `recipeSearch` takes `sortBy` of `NEWEST`, `POPULAR` or `TRENDING`, and a facet filter whose groups include `seizoen`, `menugang`, `keuken` and `momenten`. None of it is used.

## What Changes

- Clearance items carry the image Albert Heijn already returns with them, so the list can be recognised at a glance instead of read.
- The add-recipe page is useful before anything is typed: it opens on the newest Allerhande recipes, and can be switched to what is popular or trending.
- Recipes can be narrowed by the catalogue's own facets — season being the one that matters for cooking — with the available values coming from the catalogue rather than being hardcoded.
- Searching by name still works, unchanged.

## Capabilities

### Modified Capabilities
- `portal`: adds a requirement that a list meant for recognition carries imagery when the source provides it, and that finding a recipe does not require knowing its name.
- `recipe-catalogue`: adds browsing the catalogue by recency and popularity, and narrowing by its own facets.

## Impact

- `src/bonuschef/dags/defs/assets/dlt/ah_markdowns/` — the scrape asks for `imagePack`.
- `src/bonuschef/sql/models/` — `stg_ah__markdowns` and `fct_store_clearance` carry the image from the scrape rather than from the portal's own table.
- `src/bonuschef/utils/ah_recipes.py` — `sortBy` and facet filters.
- `src/bonuschef/portal/add_recipe_page.py` — a browsable default state.
- The image on an adopted recipe and on a recipe ingredient is unaffected; this is the clearance path only.
