## Context

See `proposal.md` — Why. What the code does today:

- `clearance_page.py` already computes the snapshot time (`_latest_snapshot`, converting `scraped_at` to `Europe/Amsterdam`) and already renders it as a caption in `_render_refresh_control`. The gate is the only missing piece; the timestamp plumbing exists.
- `render_clearance()` currently calls `_render_refresh_control(...)` and then falls through to `_render_metrics` and `_render_table` unconditionally.
- The "no data at all" case is already handled separately (`df is None` → an info message), so this change only needs to add the "data exists but is stale" branch.
- `profiles.yml` sets `threads: 1` for the single `default` target. The model set is 20: 6 staging, 3 intermediate, 11 marts.
- `dagster.yaml` sets `max_concurrent_runs: 1`. That is a different axis and stays as it is.

## Goals / Non-Goals

**Goals:**

- Make the stale case impossible to mistake for the current case at a glance.
- Get parallelism inside a run without touching the run-level serialisation that keeps pipelines from racing.

**Non-Goals:**

- Changing what the scrape collects or how it is stored. Stale rows remain in `fct_store_clearance` and `fct_store_clearance_history` and remain available to downstream models; this is a presentation change only.
- A general freshness framework across every page. Only clearance is perishable on an hourly scale; the Recipes and Analysis pages describe slow-moving data.
- Auto-refreshing on page load. That would fire a scrape every time the page is opened, including at 03:00, and the manual button already exists.

## Decisions

**The threshold is the trading day, not a fixed number of hours.**
A snapshot from 19:00 yesterday is worthless at 09:00 today (7 hours later is "stale") while one from 09:00 today is fine at 16:00 (7 hours later is "current") — the clock-hour distance is identical and the usefulness is opposite. What matters is whether the store has restocked and re-marked since. "Same calendar day in `Europe/Amsterdam`" captures that and needs no tuning. Rejected: a 4-hour window, which would flag the 11:00 scrape as stale by 15:00 even though it is the best data that exists that day.

**When stale, the item table is not rendered at all.**
A dimmed table, or a warning banner above a normal table, still invites reading the prices — and the failure mode is someone driving to the store for an item sold two months ago. The stale branch shows the age, what the snapshot contained (a count), and the refresh button. Rejected: rendering the table behind an expander, which is the same mistake with an extra click.

**The metrics row follows the table.**
"Max discount 45%" is exactly as misleading as the table when the data is two months old, so the stale branch suppresses `_render_metrics` too.

**`threads: 4`, not higher.**
The target VM is 2 vCPU / 4 GB, and Postgres serves the portal and Dagster's own run storage from the same instance. Four gives real parallelism across the six independent staging models without letting a rebuild starve the rest of the stack. Postgres' default `max_connections` of 100 is not a constraint at this size. Rejected: `threads: 8` — unmeasured, and on 2 vCPU the contention is likelier to cost than gain.

**The freshness rule is tested at the page level, not by asserting on Streamlit internals.**
The existing suite drives pages through `AppTest` via the `run_app` helper in `conftest.py`, with a stubbed reader. Tests inject a fresh timestamp and a stale one and assert on what is rendered — that item rows appear in one case and not the other. That keeps the test tied to observable behaviour rather than to a helper's name.

## Risks / Trade-offs

- **A scrape that fails for days leaves the page showing nothing usable**, where before it showed something. → Correct: nothing is the honest answer, and the failure alerting in `ah-token-resilience` is what surfaces the cause. The two changes are complementary; landing this one alone makes broken scraping more visible but not explained.
- **"Trading day" is wrong for a shop open past midnight.** → AH stores close by 22:00, so the calendar day and the trading day coincide. Worth revisiting only if store hours are ever modelled properly.
- **`threads: 4` could surface latent concurrency bugs in the dbt project**, particularly the `on-run-start` DDL — though that runs once per invocation, not per thread, so the hazard is between runs (already serialised) rather than between threads. → A full `dbt build` after the change is the check.
- **Faster dbt makes the daily rebuild finish sooner, shrinking the window in which the 18:00 clearance run would queue behind it.** → Purely beneficial, and does not remove the need for the serialisation, which guards the on-demand refresh path too.

## Migration Plan

1. Land both changes together; the CI session set is the gate.
2. `threads` takes effect on the next dbt invocation — no rebuild, no migration, since `profiles.yml` is read at run time.
3. The portal change takes effect on the next container rebuild (`docker compose up -d --build`), because the image bakes `src/`.
4. Rollback is `git revert` plus a rebuild. Neither change writes state.
