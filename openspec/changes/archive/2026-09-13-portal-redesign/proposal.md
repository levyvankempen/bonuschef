## Why

The portal is a dbt-mart browser wearing a Streamlit skin. Every page has the same shape: query a fact table, rename the columns, render `st.dataframe`. That shape is what "feels dev-like" means — the user is handed four tables and expected to do the join in his head.

Concretely: navigation is hidden behind a collapsed sidebar, so four pages have no affordance at all. The Laatste kans payload — a shopping list read on a phone while standing in a shop — is a ten-column grid with a horizontal scrollbar, and the product images are queried and then thrown away. The Analysis page is pipeline QA shown to the pipeline's own author: "Bonus products matched", "Avg. inflation €0.50", and a nine-column table ending in a raw boolean headed "Inflated?". Two charts plot four numbers that are printed directly beneath them.

There are also real costs behind it. A blocking HTTP fetch to ah.nl runs per ingredient inside a render loop, serially, with a 5-second timeout — ten ingredients is a fifty-second hang, and the image it fetches is already in `dim_product`. DDL runs on every keystroke in the search box. Two readers have no `WHERE` and no `LIMIT` and return every row ever recorded. Six call sites still pass `use_container_width`, which Streamlit deprecated with a removal date that has already passed.

## What Changes

- The portal gets a visual identity: a warm light theme, a display serif for headings, rounded cards, and a categorical chart palette — replacing Streamlit's stock white-and-slate, which is most of the dev-tool impression.
- Navigation moves to the top with icons, and the app speaks one language. The domain vocabulary is Dutch; the interface should be too.
- The two payloads a person actually reads — clearance items and recipe ingredients — become cards with the product images that are already being fetched and discarded, instead of grid widgets that scroll sideways on a phone.
- The Analysis page leaves the navigation. Its one genuinely valuable insight — that the advertised saving exceeds the observed one — survives as a line of context where the saving is shown.
- Charts and tables that restate numbers printed next to them are removed, along with the readers that exist only to feed them.
- The efficiency defects above are fixed.

Deliberately **not** in this change: the "what should I cook tonight" screen and the recipe-ingestion flow. Both depend on `fct_recipe_opportunity`, which depends on the live-bonus semantics and shared product crosswalk being delivered by `dbt-model-integrity` first. Building them now would mean building them on promotions that ended in July.

## Capabilities

### New Capabilities
<!-- None. -->

### Modified Capabilities
- `portal`: adds requirements covering how the portal is navigated, how it presents a list meant to be read on a phone in a shop, what it is allowed to show its user about its own internals, and the cost it may incur while rendering.

## Impact

- `.streamlit/config.toml` — new.
- `src/bonuschef/portal/app.py` — navigation, layout, naming.
- `src/bonuschef/portal/clearance_page.py` — item rendering; the freshness logic is untouched.
- `src/bonuschef/portal/recipes_page.py`, `ui.py` — ingredient rendering; chart removal.
- `src/bonuschef/portal/analysis_page.py` — removed from navigation.
- `src/bonuschef/portal/recipe_builder.py` — the render-loop image fetch and the per-rerun DDL.
- `src/bonuschef/portal/db.py` — dead readers removed, cache lifetimes, `dim_product` columns.
- `tests/unit/test_portal_*.py`, `test_ui.py` — the tests asserting on removed elements.
