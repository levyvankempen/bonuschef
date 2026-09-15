# Design

## Context

Three defects, one cause: the button models an asynchronous job as a synchronous wait.

```python
run_id = trigger_job(MARKDOWNS_REFRESH_JOB)
with st.spinner("De winkel wordt gescand…"):
    status = wait_for_run(run_id, timeout_s=180)
```

Every failure follows from those three lines.

| observed | why |
|---|---|
| spinner said "scanning" for 3 minutes while nothing ran | the run was 44th in a queue; `wait_for_run` cannot distinguish QUEUED from STARTED |
| spinner vanished after ~1 minute, no result, no error | backgrounding a phone tab drops the websocket; the session and its pending wait die together |
| data unchanged after a successful run | `.clear()` runs only in the session that waited; another session keeps its 15-minute cache |

## Goals / Non-Goals

**Goals**
- Report the run's real state, including that it has not started.
- Survive a dropped session: the run id is the state, not the session.
- Drop invalidated caches for every reader, not only the one who pressed.
- Keep the existing check that a green tick means the snapshot actually advanced.

**Non-Goals**
- Auto-refreshing on a timer. A poll button is honest and costs nothing when nobody is looking; a rerun loop on a phone in a shop is a battery drain for a job that takes a minute.
- Changing the job, the mart, or what the page shows once the data is there.

## Decisions

### 1. The run id is the state

Pressing the button stores the run id and returns immediately. Every subsequent render reads the run's status from Dagster and reports it. Nothing is held across the interaction except an id, which is exactly what survives a session reset — and what does not survive it is a pending network wait.

This is the shape the review dialog already uses (`render_rebuild_status`), and the two should not diverge: a person who has corrected an ingredient and a person who has refreshed clearance are asking the same question, *"is it done yet?"*, and it should be answered the same way.

### 2. QUEUED is reported as queued

`max_concurrent_runs: 1` is deliberate — dbt's DDL is not safe to run twice at once against one Postgres — so waiting is a normal state, not an anomaly. Saying "de winkel wordt gescand" while a run waits behind a backfill is not a small imprecision: it sent an hour of debugging at the wrong component. The page now says *in de wachtrij*.

### 3. Caches are cleared on observing completion, not on having waited

`st.cache_data.clear()` is global, so whichever session first *observes* the terminal state clears for everyone. Tying it to having waited is what made a successful refresh invisible to a phone that had slept through it.

### 4. The snapshot check stays

A Dagster run that scrapes nothing new still exits SUCCESS, and dbt still rebuilds the mart from unchanged rows. The existing `_SNAPSHOT_BEFORE_KEY` comparison — a green tick only when the snapshot actually advanced — is kept exactly as it is. Making the reporting asynchronous must not weaken the one check that stops the page claiming freshness it did not verify.

## Risks / Trade-offs

**A poll button is a manual step.** Someone may press *Nu ophalen* and walk away without pressing *Ververs*. They lose nothing — the next page load reports the outcome, because the state is the run id — but they do not see it live. Accepted deliberately over a rerun loop: this page is opened in a shop, on a phone, and a timer that reruns a Streamlit script every few seconds to watch a one-minute job is the wrong trade.

**A run id in session state still does not survive a *new* session.** Closing the tab entirely loses the handle, and the page falls back to the freshness banner it already had — which reads the snapshot itself and is the more reliable signal anyway. This change makes the common interruption survivable, not every one.
