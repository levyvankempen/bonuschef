## Context

See `proposal.md` — Why. What the code does today:

- `app.py` uses `st.navigation` at its default `position="sidebar"` together with `initial_sidebar_state="collapsed"`, so the four pages are behind a hamburger. Titles mix English and Dutch. `layout="wide"` stretches tables on a laptop for an app used mostly on a phone.
- Streamlit 1.50 supports exactly one custom theme — `CustomThemeCategories` has only `SIDEBAR` — so `config.toml` cannot define a light/dark pair. Setting colours overrides the viewer's OS preference.
- `clearance_page.py` renders a ten-column `st.dataframe`; `db.py`'s clearance query already selects `image_url`, which is then dropped.
- `recipe_builder.py` calls `_fetch_product_image` inside the ingredient render loop — `urlopen` with `timeout=5`, serial, cached only an hour — and calls `ensure_recipe_tables` / `ensure_product_images_table` unconditionally on every rerun.
- `db.py`'s `read_price_changes` and `read_product_prices` have no `WHERE` and no `LIMIT`; their only callers are the Analysis page.
- Every reader is `@st.cache_data(ttl=60)`, against pipelines that run hourly at best.
- The freshness apparatus in `clearance_page.py` — the trading-day rule, the 11:00 first-scrape branch, the refresh-didn't-move-the-snapshot warning — is the most carefully reasoned code in the portal and is not touched by this change.

## Goals / Non-Goals

**Goals:**

- Change what the portal *feels* like without changing what it *knows*, so the risk stays in presentation rather than in data.
- Remove work that costs the user time and returns nothing.

**Non-Goals:**

- The "what should I cook tonight" screen and the `fct_recipe_opportunity` mart behind it. They are the actual product, and they depend on live-bonus semantics that `dbt-model-integrity` has not delivered yet — built today they would rank recipes by promotions that ended in July.
- Recipe ingestion by paste or URL. It is the reason only two recipes exist, and it is worth its own change rather than a paragraph in this one.
- A dark theme. Streamlit 1.50 permits one theme; picking one and moving on is the proportionate answer for a single-user app.
- Any change to the freshness logic.

## Decisions

**Stay on Streamlit and spend the effort on substance.**
The alternative — FastAPI plus a real frontend — buys control the end goal does not need. That goal is a push notification and a short ranked list, not a dashboard. A theme plus card layouts closes most of the gap for a fraction of the work, and leaves the option open.

**Warm neutrals, not white.**
Streamlit's stock `#FFFFFF` background with `#262730` blue-slate text is most of the dev-tool read. Warm off-white paper, warm near-black ink, a deep leaf-green primary, and a sand secondary give it a cookbook register instead. The semantic colours matter as much: stock `#ff4b4b` and `#ffa421` are the loudest "this is a Streamlit app" tell anywhere in the product, and they are exactly what the clearance urgency badges would use.

**Cards, not grids, for the two lists people read.**
`st.dataframe` is a spreadsheet widget: sort arrows, a resize handle, a fullscreen button, and horizontal scrolling. For two recipes or a clearance list on a phone, all of that is noise around four facts. `st.container(border=True, horizontal=True)` wraps on narrow screens where `st.columns` does not, and is one element per row rather than six.

**The Analysis page leaves the navigation rather than being deleted.**
Its content is pipeline QA — match rates, inflation averages, a raw `Inflated?` boolean — shown to the pipeline's own author while he is deciding what to eat. But the underlying comparison is the project's thesis, and a diagnostic surface has genuine value during the Proxmox migration. Removing it from `st.navigation` keeps it reachable by URL while taking it off the product surface. Deleting the file would throw away a debugging tool a week before it is most needed.

**Cut charts that restate adjacent numbers.**
The cost-history line chart plots weekly totals for two recipes; the breakdown bar chart plots four values printed directly beneath it. Neither changes a decision. Their readers go with them, which is also how `read_price_changes` — an unbounded full-table scan — leaves the codebase.

**Cache lifetimes follow the pipelines, not a default.**
`ttl=60` against an hourly scrape means a reload 61 seconds later re-queries data that has not moved in forty minutes, while a genuine refresh can wait a minute to appear. `ttl=900` plus the explicit `.clear()` the refresh path already performs is correct in both directions.

**`use_container_width` is deleted, not replaced, on dataframes.**
`st.dataframe`'s `width` already defaults to `"stretch"`, so the kwarg is redundant as well as deprecated. `st.button` defaults to `"content"`, so that one becomes `width="stretch"`. `st.altair_chart` has no `width` parameter at all in 1.50 and is not deprecated — passing `use_container_width=True` there is merely redundant.

**The product image comes from the warehouse, not from ah.nl at render time.**
`dim_product.image_url` already holds it. Fetching it again inside a render loop is both the largest latency defect in the app and unnecessary; the scrape stays only on the save path, and only when the stored value is null.

## Risks / Trade-offs

- **Cards use more vertical space than a grid**, so a 120-item clearance list becomes a long scroll. → That list is filtered by category and read a few items at a time in a shop; a grid that needs horizontal scrolling on a phone is worse than a long vertical one. Ordering by what is nearly gone matters more than density.
- **Removing the Analysis page hides the inflated-price comparison**, which is the project's thesis and something the user is proud of. → It is not removed, only relocated: the discrepancy moves to where the saving is shown, which is where it is actionable. The page stays reachable.
- **A theme is a matter of taste and this one is chosen, not offered.** → Single user; the values are six lines of `config.toml` and trivially changed. Presenting options would cost more of his time than changing it later.
- **Dropping `read_price_changes` and `read_product_prices` removes capability, not just clutter.** → Both are unbounded scans whose only consumer is leaving the navigation. If price-history exploration is wanted later it should be a bounded query written for that purpose.

## Migration Plan

1. Land the repo changes; the CI session set is the gate.
2. `.streamlit/config.toml` is read at process start, so the theme takes effect on the next container start — `docker compose up -d --build streamlit`.
3. Rollback is `git revert` plus the same rebuild. Nothing here writes state, and no query result changes.
