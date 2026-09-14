## 1. Clearance images

- [ ] 1.1 Ask for `product { imagePack { medium { url width height } } }` in the clearance scrape and carry a chosen URL onto each row; read it defensively, since a missing pack, an empty list or an absent size must degrade to no image rather than fail a scrape over a picture; verify unit tests cover all three
- [ ] 1.2 Carry `image_url` through `stg_ah__markdowns` into `fct_store_clearance`, sourcing it from the scrape rather than the `product_images` join that yields NULL for every one of the 121 current rows; verify the mart shows a non-null image for most items after a scrape
- [ ] 1.3 Verify the clearance card renders the image and still renders cleanly when one is missing — the card code already expects it, so this is about the data arriving

## 2. Browsing the catalogue

- [ ] 2.1 Add `sortBy` to `search_recipes`, validating it against the three values the catalogue accepts before the request is sent; an unknown ordering must not surface as the catalogue being unreachable, which is how the `PageSize` scalar failed; verify a test asserts an invalid ordering raises locally with no HTTP call
- [ ] 2.2 Add facet filtering, passing `{group, values}` through to the query; verify a test asserts the filter reaches the outgoing variables
- [ ] 2.3 Add a call returning the catalogue's own facet groups and values with counts, so the options are never hardcoded; verify a test asserts the shape is parsed and that an unexpected shape fails rather than yielding silently empty options

## 3. The page

- [ ] 3.1 Open the add-recipe page on the newest catalogue recipes rather than an empty search box, so it answers "what could I cook" and not only "do you have this"; verify a test asserts recipes render before anything is typed
- [ ] 3.2 Let the ordering be switched between newest, popular and trending; verify a test asserts switching re-queries with the chosen ordering
- [ ] 3.3 Offer a season filter whose values come from the catalogue; verify a test asserts the values are read rather than hardcoded
- [ ] 3.4 Keep search working and have it replace the browsable list rather than filter it; verify the existing search tests still pass
- [ ] 3.5 Report an unreachable catalogue on arrival as unreachable, distinctly from there being no recipes; verify a test asserts the two messages differ

## 4. Gate

- [ ] 4.1 `uv run pytest`, no new skips, no network
- [ ] 4.2 `uv run ty check src tests noxfile.py`, clean
- [ ] 4.3 `uv run ruff check` and `ruff format --diff`, clean
- [ ] 4.4 `uv run sqlfluff lint` over the models, clean
- [ ] 4.5 Re-scrape and confirm clearance items carry images; browse the catalogue in the running portal and adopt a recipe found without typing
