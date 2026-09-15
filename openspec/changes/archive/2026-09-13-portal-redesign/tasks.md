## 1. Identity

- [x] 1.1 Create `.streamlit/config.toml` with a warm light `[theme]` — off-white paper background, warm near-black text, deep leaf-green primary, sand secondary, tan borders — plus semantic green/orange/red that replace Streamlit's stock `#ff4b4b`/`#ffa421`, a display serif for headings with a grotesque for body, a tightened heading size ramp, and rounded corners; verify a test asserts the file parses and defines the theme keys, so a malformed value cannot silently fall back to the stock look
- [x] 1.2 Set a categorical chart palette in the theme so any surviving chart stops rendering in Vega default blue; verify it is present in the parsed config

## 2. Navigation and framing

- [x] 2.1 Move `st.navigation` to `position="top"` in `app.py` and give each page an icon, so four destinations stop hiding behind a collapsed sidebar; verify a test asserts the navigation is not sidebar-positioned
- [x] 2.2 Make every page title Dutch, matching the domain vocabulary the data already uses; drop "Portal" from the page title; verify a test asserts no English titles remain in the navigation
- [x] 2.3 Change `layout` from `wide` to `centered` so the laptop gets a readable measure and the phone is unaffected; verify the portal tests still pass

## 3. The lists people read

- [x] 3.1 Replace the ten-column `st.dataframe` in `clearance_page.py` with one bordered card per item — image, name, brand and size, current price prominent, original price and percentage secondary — using the `image_url` the clearance query already selects and currently discards; verify an `AppTest` case asserts item content is rendered and that no dataframe element remains on the fresh path
- [x] 3.2 Surface urgency on the card: low stock and a same-day expiry date, since those are what make an item worth acting on now; verify tests cover an item with low stock and one expiring today
- [x] 3.3 Order clearance items by what is most likely to be gone rather than by discount alone; verify a test asserts the ordering
- [x] 3.4 Replace the six-column-per-row ingredient loop in `recipes_page.py` with cards that wrap on a narrow screen; verify the recipes page tests still pass
- [x] 3.5 Remove the "Matched to tracked" metric from the clearance page — it is a join-coverage statistic about the pipeline — and verify the existing test asserting its value is updated rather than deleted wholesale

## 4. Removing what does not serve the user

- [x] 4.1 Remove the Analysis page from `st.navigation` while leaving the module reachable, so it remains a diagnostic surface during the Proxmox migration without occupying the product; verify a test asserts it is absent from the navigation
- [x] 4.2 Move the advertised-versus-observed saving discrepancy to where the saving is shown, as a line of context rather than a nine-column table with a raw `Inflated?` boolean; verify a test asserts the wording appears when the two figures differ
- [x] 4.3 Delete the cost-history line chart and the cost-breakdown bar chart, which plot values printed directly beside them, along with their helpers in `ui.py`; verify `test_ui.py` is updated and the remaining helpers still pass
- [x] 4.4 **Deviated deliberately.** Task 4.1 keeps the Analysis page reachable as a diagnostic surface, so these readers still have a consumer and deleting them would break it. The spec requirement is about boundedness, not deletion, so `read_price_changes` is now `LIMIT`-bounded instead. `read_product_prices` is parameterised by product and already bounded by its filter. Revisit if the page is ever deleted outright

## 5. Cost of rendering

- [x] 5.1 Add `image_url` and `price` to `dim_product` and to `list_products`, then remove the `_fetch_product_image` call from the ingredient render loop in `recipe_builder.py`, keeping the scrape only on the save path and only when the stored value is null; verify a test asserts no network call occurs during rendering
- [x] 5.2 Remove the unconditional `ensure_recipe_tables` and `ensure_product_images_table` calls that run DDL on every rerun, including every keystroke in the search box; verify a test asserts the page renders without issuing schema statements
- [x] 5.3 Raise reader cache lifetimes from 60 seconds to 15 minutes, matching the pipelines that produce the data, and confirm the explicit `.clear()` on the refresh path still makes a manual refresh immediate; verify the existing refresh test still passes
- [x] 5.4 Delete the deprecated `use_container_width` kwarg from every `st.dataframe` call, change the `st.button` occurrence to `width="stretch"`, and drop the redundant one from `st.altair_chart` calls; verify no occurrence remains and no deprecation warning appears in the test output

## 6. Gate

- [x] 6.1 Run `uv run pytest` and confirm the suite passes with no new skips and no Streamlit deprecation warnings
- [x] 6.2 Run `uv run ty check src tests noxfile.py` and confirm it is clean
- [x] 6.3 Run `uv run ruff check` and `ruff format --diff` over `src tests noxfile.py`, both clean
- [x] 6.4 Rebuild the portal container and confirm it serves, the theme is applied, and the clearance page renders cards
