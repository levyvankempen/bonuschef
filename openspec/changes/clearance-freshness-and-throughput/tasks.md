## 1. dbt throughput

- [ ] 1.1 Change `threads: 1` to `threads: 4` in `src/bonuschef/sql/profiles.yml`; verify a test asserts the configured thread count is greater than one, so a silent revert to serial building is caught
- [ ] 1.2 Run a full `uv run dbt build --project-dir src/bonuschef/sql --profiles-dir src/bonuschef/sql` against the running Postgres and confirm it succeeds with no concurrency errors; note the wall-clock difference against the serial baseline

## 2. Clearance freshness

- [ ] 2.1 Add a freshness predicate to `src/bonuschef/portal/clearance_page.py` deciding whether a snapshot falls within the current trading day in `Europe/Amsterdam`; verify unit tests cover same-day, previous-evening, and months-old timestamps against an injected clock rather than wall time
- [ ] 2.2 Branch `render_clearance()` so a stale snapshot renders neither `_render_table` nor `_render_metrics`, showing instead the snapshot's age, how many items it held, and the existing refresh control; verify an `AppTest` case asserts no item rows are rendered when the snapshot is stale
- [ ] 2.3 Verify the three states stay distinguishable — no data ever collected, stale data, fresh data — with a test asserting each renders its own message and that the "no data" path is unchanged
- [ ] 2.4 Verify a successful refresh moves the page from the stale branch to the fresh branch without a manual reload, extending the existing refresh-path test
- [ ] 2.5 Verify a failed refresh reports the failure and still does not render the stale items, extending the existing failure-path test
- [ ] 2.6 Confirm the capture time is shown in Dutch local time in both the fresh and stale branches; verify the existing `_latest_snapshot` timezone assertion still covers it

## 3. Gate

- [ ] 3.1 Run `uv run pytest` and confirm the full suite passes with no new skips and no network access
- [ ] 3.2 Run `uv run ty check src tests noxfile.py` and confirm it is clean
- [ ] 3.3 Run `uv run ruff check` and `uv run ruff format --diff` over `src tests noxfile.py` and confirm both are clean
- [ ] 3.4 Rebuild and confirm in the running portal that the current two-month-old snapshot renders as stale rather than as a normal table
