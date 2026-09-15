## Why

The clearance page's **Nu ophalen** button treats an asynchronous job as a synchronous wait, and all three of its defects were found by using it on a phone rather than by any test.

Pressing it triggers a Dagster run and blocks on `wait_for_run` behind a spinner reading *"De winkel wordt gescand…"*. On the day this was exercised in earnest the run was **44th in a queue** behind a backfill, and the page said the store was being scanned for three minutes while nothing whatsoever was happening. Queued and running are different facts and the page cannot tell them apart.

Worse on the device it is built for: backgrounding a tab on a phone drops Streamlit's websocket, the session resets, and the pending wait dies with it — no result, no error, no record. The outcome banner lives in `st.session_state`, which does not survive that. And even after a successful run, `read_store_clearance` keeps serving its 15-minute cache to any session that did not do the waiting, so the data appears not to have moved.

The review dialog already solved this shape: report the run's real state, poll it, and clear the caches when it finishes. The clearance button should work the same way.

## What Changes

- The refresh reports what the run is actually doing. A queued run says it is queued — with runs serialised instance-wide it may genuinely be waiting behind a scrape, and calling that "scanning" hides a real cause.
- The outcome survives a dropped session. The run is tracked by id, so a phone that slept through the wait still learns how it went.
- A finished run drops the caches it invalidated, for the session that reads next as well as the one that pressed the button.
- The existing honesty check is kept: a green tick still means the snapshot actually advanced, not merely that a job exited SUCCESS.

## Capabilities

### Modified Capabilities
- `portal`: strengthens "The portal finishes its own work" so that reporting the outcome survives the session, and a queued run is distinguishable from a running one.

## Impact

- `src/bonuschef/portal/clearance_page.py` — the refresh control becomes non-blocking.
- No change to the Dagster job, the mart, or what the page displays once the data is there.
