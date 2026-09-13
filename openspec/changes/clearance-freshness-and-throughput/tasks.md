## 1. dbt throughput

- [x] 1.1 Replace `threads: 1` in `src/bonuschef/sql/profiles.yml` with `DBT_THREADS` read from the environment, defaulting to 2 — measured against the 2 vCPU target, where Postgres does the same ~21 CPU-seconds whatever the thread count; verify a new test asserts the default is above 1 and no higher than 4, and that it stays host-configurable
- [x] 1.2 Run a full `dbt build` against the running Postgres and confirm no concurrency errors; measured PASS=89 WARN=0 ERROR=0 at 12.7s against a 17.5s serial baseline, and confirmed `on-run-start` runs once per invocation rather than once per thread, so the non-idempotent DDL cannot race

## 2. Clearance freshness

- [x] 2.1 Add a freshness predicate to `src/bonuschef/portal/clearance_page.py` deciding whether a snapshot falls within the current trading day in `Europe/Amsterdam`; verify unit tests cover same-day, previous-evening, and months-old timestamps against an injected clock rather than wall time
- [x] 2.2 Branch `render_clearance()` so a stale snapshot renders neither `_render_table` nor `_render_metrics`, showing instead the snapshot's age, how many items it held, and the existing refresh control; verify an `AppTest` case asserts no item rows are rendered when the snapshot is stale
- [x] 2.3 Verify the three states stay distinguishable — no data ever collected, stale data, fresh data — with a test asserting each renders its own message and that the "no data" path is unchanged
- [x] 2.4 Verify a successful refresh moves the page from the stale branch to the fresh branch without a manual reload, extending the existing refresh-path test
- [x] 2.5 Verify a failed refresh reports the failure and still does not render the stale items, extending the existing failure-path test
- [x] 2.6 Confirm the capture time is shown in Dutch local time in both the fresh and stale branches; verify the existing `_latest_snapshot` timezone assertion still covers it

## 3. Gate

- [x] 3.1 Run `uv run pytest` and confirm the full suite passes with no new skips and no network access
- [x] 3.2 Run `uv run ty check src tests noxfile.py` and confirm it is clean
- [x] 3.3 Run `uv run ruff check` and `uv run ruff format --diff` over `src tests noxfile.py` and confirm both are clean
- [x] 3.4 Rebuild and confirm the portal serves correctly. Note: the stale path can no longer be verified by hand — the mart was refreshed earlier today, so the live page correctly renders *fresh*, and manufacturing staleness would mean backdating production data. The stale, not-yet-scraped, empty and NaT paths are covered by tests instead
