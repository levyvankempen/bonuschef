## Why

Two unrelated problems, both cheap, both currently costing real value.

The Laatste kans page renders clearance items as a normal table no matter how old they are. Right now it is showing a snapshot from 2026-07-06 — two months stale — under a one-line grey caption. For data whose entire premise is that discounts deepen through the day and stock sells out within hours, presenting a stale snapshot as an ordinary table is actively misleading: the page fails toward showing something wrong rather than showing nothing.

Separately, `src/bonuschef/sql/profiles.yml` sets `threads: 1`, so dbt builds all 20 models strictly one at a time. The DAG has real width to exploit — the six staging models have no interdependencies at all — so this is wall-clock spent for nothing. It is easy to mistake this for the run-level serialisation added in `harden-selfhost-config`, but that limit governs concurrent *runs*; this one governs parallelism *within* a run, and they are independent.

## What Changes

- The clearance page treats staleness as structural rather than cosmetic: past a freshness threshold it stops presenting items as current, and says plainly that the data is stale and how old it is.
- The freshness threshold is expressed in terms of the trading day, because a snapshot from yesterday evening is worthless regardless of whether it is 14 or 20 hours old.
- dbt's thread count rises from 1 to 4, so independent models build concurrently within a run.

## Capabilities

### New Capabilities
- `portal`: how the portal presents pipeline-produced data to a person — in particular its obligation not to present perishable data as current once it has aged out.

### Modified Capabilities
- `scheduling`: adds a requirement covering parallelism *within* a run, alongside the existing requirement covering concurrency *between* runs.

## Impact

- `src/bonuschef/portal/clearance_page.py` — the render path gains a freshness gate; `_render_refresh_control` already computes the snapshot timestamp it needs.
- `src/bonuschef/sql/profiles.yml` — one line.
- `tests/unit/test_portal_clearance_page.py` — cases for fresh, stale and absent data.
- No database schema, no dbt model, and no change to what the scrape collects. Items are still recorded and still available to downstream models when stale; only the portal's presentation changes.
