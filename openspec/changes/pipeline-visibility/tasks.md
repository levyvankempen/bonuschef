# Tasks

## 1. Evaluate the declared freshness

- [x] 1.1 A Dagster op that runs `dbt source freshness` and fails when any source is in `error` state, warning on `warn`
- [x] 1.2 Its own job, not a step in an existing one — a stale feed must not fail the rebuild, since the rebuild is what keeps the last good data serving
- [x] 1.3 A schedule matching the tightest declared threshold that still leaves room for the feed's own cadence
- [x] 1.4 Tests: the op fails on an `error` result, warns without failing on `warn`, and does not treat a missing `loaded_at` as fresh

## 2. Read the pipeline's health

- [ ] 2.1 `read_pipeline_health` — last success per job, from the `runs` table already in the portal's Postgres
- [ ] 2.2 Judge each job against its own cadence rather than one global threshold
- [ ] 2.3 Fail soft: a schema change or an unreachable database degrades the page to what it does today rather than erroring

## 3. Surface it

- [ ] 3.1 Render nothing while every job is succeeding — a permanent indicator is furniture
- [ ] 3.2 Name the job and when it last worked when one is overdue
- [ ] 3.3 Call out `token_heartbeat` separately: its recovery needs a browser and cannot be done unattended
- [ ] 3.4 Put it on the default destination, where the owner already looks

## 4. Stop trusting the source when the mart is what matters

- [ ] 4.1 `read_bonus_feed_loaded_at` reads the source table, so a successful load followed by a failed rebuild reads as fresh. Judge the answer's freshness on the mart that produced it
- [ ] 4.2 A test that a fresh source with a stale mart is reported stale

## 5. Verification

- [ ] 5.1 Full suite, ruff, ty
- [ ] 5.2 `dbt source freshness` runs green against the live warehouse
- [ ] 5.3 The health surface shows nothing on a healthy stack, and reports a job made overdue on purpose
