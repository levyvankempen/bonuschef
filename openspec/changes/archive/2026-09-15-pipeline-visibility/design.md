# Design

## Context

Both halves answer one question: *how would anyone know this had stopped working?*

Today the honest answer is "when the portal's clearance banner goes stale, a day later" — and only for clearance. Everything else fails silently:

| failure | what emits an event | who sees it |
|---|---|---|
| a run fails | `RUN_FAILURE` → ntfy | nobody (deliberately unsubscribed) |
| a run is never launched | nothing | nobody |
| a sensor tick throws | a FAILURE tick, not a run | nobody |
| a feed stops arriving | nothing — thresholds are declared but never evaluated | nobody |
| dlt loads, dbt fails | nothing — the source stays fresh, the marts freeze | nobody |

The last row is the nastiest: `read_bonus_feed_loaded_at` reads `ah__bonus_products`, the *source* table. A successful load followed by a failed rebuild leaves it fresh, the banner quiet, and every mart stale.

## Goals / Non-Goals

**Goals**
- Evaluate the freshness thresholds that are already declared.
- Make the failures that emit no event visible where the owner already looks.
- Work with no notification channel subscribed, because none is.

**Non-Goals**
- A monitoring stack. This is a personal project on a 2 GB guest.
- Re-opening the ntfy decision. The owner declined it knowing what it does and does not buy; this makes the portal a sufficient surface regardless.
- Alerting on *every* job. Only ones whose silence would leave a wrong or frozen answer on screen.

## Decisions

### 1. Freshness gets its own job, not a step inside another

`dbt source freshness` is a separate command from `dbt build`; folding it into an existing asset would make a stale feed fail the rebuild, which is backwards — the rebuild is exactly what you still want when a feed is late, so the last good data keeps serving.

So: its own job, its own schedule, failing on its own. That failure is then one more row in the run table the portal reads, which is how it becomes visible.

### 2. The portal reads the Dagster run table directly

It is in the same Postgres the portal already connects to. One query over `runs` gives last-success-per-job, which covers every failure mode in the table above including the ones that emit no event — because "no successful run since" is a fact about absence, and absence is what none of the event-driven paths can report.

This deliberately couples the portal to Dagster's schema. The alternative is the GraphQL API, which is a second network dependency that fails exactly when things are broken. A schema change on a pinned Dagster version is a smaller risk than a health check that cannot run during an incident.

### 3. Silence when healthy

A tile that is always present is furniture and stops being read. Nothing renders while every job is succeeding on its cadence; a job appears only when it is overdue.

### 4. The credential is called out separately

Every other failure recovers by itself or by re-running a job. `token_heartbeat` failing means the AH credential is heading for expiry, and its recovery needs an interactive browser login behind hCaptcha — the one thing in this system that cannot be done unattended. It has already expired twice from disuse. It gets its own sentence.

### 5. Each job is judged on its own cadence

An hourly scrape overdue by two hours is a problem; a weekly pool refresh two hours "late" is not. The thresholds come from the schedules themselves rather than one global number.

## Risks / Trade-offs

**A query against Dagster's internal schema.** `runs` is stable across the 1.x line and the version is pinned (`dagster-postgres <0.28`, load-bearing and already documented). If it moves, the health tile breaks — it is read-only and its failure is caught, so the page degrades to what it does today rather than erroring.

**Freshness failures are only as visible as the portal.** With no channel subscribed, a stale feed is noticed next time the page is opened rather than within the hour. That is strictly better than today, and the owner has chosen the trade.
