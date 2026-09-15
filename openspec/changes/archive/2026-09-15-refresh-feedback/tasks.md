# Tasks

## 1. The refresh becomes non-blocking

- [x] 1.1 Pressing **Nu ophalen** stores the run id and returns, instead of blocking on `wait_for_run` behind a spinner
- [x] 1.2 Keep the snapshot-before value alongside it, so the existing "did the data actually move" check survives the change
- [x] 1.3 Failure to *start* the run is still reported immediately — that one is synchronous and needs no run id

## 2. Reporting the run

- [x] 2.1 Read the status from Dagster on every render, not from session state: an id survives a session reset, a pending wait does not
- [x] 2.2 QUEUED says **in de wachtrij**, not "scanning". Runs are serialised deliberately, so waiting is a normal state and describing it as scanning sent an hour of debugging at the wrong component
- [x] 2.3 STARTED says the store is being scanned, which is then true
- [x] 2.4 A terminal state clears the run id so the notice does not persist, and reports success, failure or cancellation distinctly
- [x] 2.5 A **Ververs** button to poll on demand; no rerun loop, because this page is read on a phone in a shop
- [x] 2.6 Losing sight of the run is not an error — the scrape either happened or did not, and the freshness banner reads the snapshot itself

## 3. Caches

- [x] 3.1 Clear `read_store_clearance` and `read_last_scrape_time` when a session *observes* completion, not when it waited for it
- [x] 3.2 Verify the effect is global rather than per-session, since that is the whole point

## 4. Tests

- [x] 4.1 A queued run renders differently from a running one
- [x] 4.2 The outcome is reported from the run id alone, with no prior wait in the session
- [x] 4.3 A finished run clears both caches exactly once and drops the id
- [x] 4.4 A failed run says so without implying the data moved
- [x] 4.5 An unreachable run is not surfaced as an error
- [x] 4.6 The existing snapshot-advanced check still governs the green tick
- [x] 4.7 The whole existing clearance suite still passes — this is a change to how an outcome is reported, not to what the page shows
