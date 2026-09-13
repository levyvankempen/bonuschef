## Context

See `proposal.md` — Why. The constraints that shape the approach:

- `docker-compose.yml` defines four services: `postgres` (`postgres:16`), and `dagster-webserver`, `dagster-daemon`, `streamlit`, all three built from the repo `Dockerfile` (`ghcr.io/astral-sh/uv:python3.12-bookworm`).
- `postgres` already has a healthcheck; the three app services have none.
- `dagster.yaml` declares `QueuedRunCoordinator` with no limits. Dagster's default `max_concurrent_runs` is **10**, so nothing currently serialises runs.
- `Dockerfile` copies `dagster.yaml` into `/app/dagster_home/`, and both Dagster services mount the named volume `dagster_home` over that directory.
- `src/bonuschef/sql/dbt_project.yml` runs five `CREATE TABLE IF NOT EXISTS` statements plus `seed_default_recipes()` in `on-run-start`, on *every* dbt invocation, and materialises marts as `table`.
- The suite must run with no database and no network (`tests/conftest.py` stubs `requests`). Nothing may start a container.
- `k8s/` is not the deployment path and stays untouched.
- Requirements live in `specs/`; they are not restated here.

## Goals / Non-Goals

**Goals:**

- Express every deployment guarantee as data in tracked files, so a test can assert it by parsing rather than by running anything.
- Make the per-service rules hold for *every* service, including ones added later.
- Close the concurrency hole that retiming the daily refresh opens, at its root rather than by choosing a luckier clock time.

**Non-Goals:**

- Verifying a healthcheck command against a live container, or asserting Docker's runtime behaviour. That needs a daemon and belongs to host setup.
- Acting automatically on an unhealthy container, per-service memory limits, or any change to `k8s/` or the dbt models.
- Host-level configuration (`/etc/docker/daemon.json`, `systemctl enable docker`). Recorded as preconditions in the Migration Plan, not implemented here.

## Decisions

**Runs are serialised with `max_concurrent_runs: 1`, rather than dodging the collision with a different clock time.**
Moving the daily refresh to 17:30 puts it 30 minutes before an hourly clearance run. `daily_refresh` selects `ah__bonus_products | (all - dlt)` — every dbt model — which is a strict superset of the four assets `markdowns_refresh` touches (asserted in `tests/unit/test_definitions.py`). Two concurrent dbt invocations then collide two independent ways: the `on-run-start` `CREATE TABLE IF NOT EXISTS` statements are not race-safe in Postgres (they surface as `duplicate key value violates unique constraint "pg_type_typname_nsp_index"`), and two rebuilds of the same `table`-materialised mart deadlock on the create/rename/drop sequence. Alternative considered and rejected: scheduling the daily at 21:00, after the clearance window closes. That avoids *this* collision but leaves the stack one schedule edit away from the next one, and the portal's on-demand "Refresh now" can still overlap a scheduled run at any hour — so the time-based fix is not actually a fix. Accepted cost: an hourly clearance run can start late when the daily overruns, and `wait_for_run` in `portal/dagster_client.py` (default 180s) may report a queued run as still pending. That is the correct behaviour to show the operator, and it is why the spec requires queueing rather than rejection.

**`daily_refresh_job` gains a retry policy.**
`markdowns_refresh_job` already has `RetryPolicy(max_retries=2, delay=60)`; `daily_refresh_job` has none. Without it the asymmetry is perverse: under any contention the hourly job survives and the *daily* job is the one that dies, silently, while alerting is deferred.

**`dagster.yaml` is bind-mounted read-only, not baked into the image.**
Docker seeds a named volume from image content only when the volume is empty, so the `dagster_home` volume masks the Dockerfile's copy from the second deployment onward. Every `dagster.yaml` change in this design — the concurrency limit, the storage block — would otherwise appear applied and not be. `- ./dagster.yaml:/app/dagster_home/dagster.yaml:ro` on both Dagster services fixes it, and the Compose test asserts the mount so it cannot regress. The `Dockerfile` copy stays, so the image is still self-contained for a bare `docker run`.

**Dagster storage moves to the existing Postgres.**
With no `storage:` block, run, event and schedule storage is SQLite inside `dagster_home` — written concurrently by the webserver, the daemon and every run subprocess, across two containers sharing one volume. `database is locked` is the standard outcome and gets likelier as run volume grows. Postgres is already running and already a dependency of both services. This is a `dagster.yaml` change, so it is only effective once the bind mount above exists — the two are ordered.

**Health probes use the exec form with a bare `python`, and target `127.0.0.1`.**
Exec form (`test: [CMD, python, -c, ...]`) rather than `CMD-SHELL`: there is no shell, so the Python one-liner carries no quoting hazard — the risk a shell form would introduce is a typo that makes a container permanently unhealthy. `python` (not `python3`, not `uv run python`) is correct: the image's official-image lineage symlinks `/usr/local/bin/python`, and `urllib` is stdlib, so the venv is irrelevant. `uv run` would be actively wrong here — it re-resolves and validates the environment and takes a lock on `.venv` on every probe, which at a 30-second interval, concurrently with a dbt or dlt run in the same container, is a hazard, and it can reach the network, which the spec's no-outbound-access scenario forbids. This warrants a comment in the compose file so nobody "corrects" it later. `127.0.0.1` rather than `localhost` because both servers bind IPv4 only, and `localhost` may resolve `::1` first and pay a failed connect.

**Probe endpoints: `/server_info` (Dagster) and `/_stcore/health` (Streamlit).**
Both confirmed against the pinned versions, and both are static enough to answer while the database is down — which is what the "database is unavailable" scenario requires. Dagster's handler returns three version strings and never touches the instance. Streamlit's health route reports whether the runtime has left its initial state; the deprecated `healthz` path sets response headers only, so there is no redirect to worry about. Streamlit's `/_stcore/script-health-check` was rejected precisely because it *does* execute the script and would tie health to the database.

**Deployment guarantees are tested by parsing YAML, iterating every service.**
`tests/unit/test_compose_config.py` loads `docker-compose.yml` with `yaml.safe_load` and asserts over every entry of `services`, so a service added later is covered rather than a hard-coded list of four. Repo root is resolved with `Path(__file__).resolve().parents[2]`, matching `tests/unit/test_definitions.py`. Rejected: `docker compose config` as a subprocess (needs the Docker CLI in CI, and would degrade to a skip); testcontainers (violates the no-network rule outright). This asserts the file says the right thing, not that Docker does the right thing — accepted, because it catches the realistic regression (new service, forgotten policy) at zero cost, and the alternative needs infrastructure the suite may not touch.

**`pyyaml` *and* `types-PyYAML` become dev dependencies.**
PyYAML is resolvable today as a transitive of `dagster-shared` (a runtime dependency) and of dbt, but a test importing it should declare it. `types-PyYAML` is not optional: `ignore_missing_imports = true` does **not** suppress mypy's `import-untyped`, PyYAML ships no `py.typed`, and `noxfile.py` runs mypy over `tests` — so `pyyaml` alone turns CI red. House precedent is `types-requests`. Both are already in `uv.lock`, but the lock must be committed with the change: `Dockerfile` uses `uv sync --frozen`, which silently builds from a stale lock rather than erroring.

**The port-binding assertion checks the host-interface prefix on every published port.**
Asserting exact literals would pass for the wrong reason if someone later added a second, unbound mapping. Now that all three services bind loopback, the test can require a `127.0.0.1:` prefix on every published mapping in the file, which also covers services added later.

**`dagster-daemon` gets a restart policy and log rotation, but no healthcheck.**
It serves no HTTP port. The test asserts the two web services *have* one; it deliberately does not assert the daemon lacks one, which would promote this rationale to a contract and break the day someone adds `dagster-daemon liveness-check`.

## Risks / Trade-offs

- **Serialising runs makes the portal's "Refresh now" feel slower**, and `wait_for_run`'s 180s default can elapse while a run is still queued behind the daily. → The spec requires it be reported as pending rather than rejected; the portal already distinguishes the states. Revisit only if it becomes annoying in practice.
- **Binding all three ports to loopback breaks LAN access** — a DBeaver session, or the portal from a phone. → Intended, and called out in Impact. Tailscale or `ssh -L` is the replacement, and the spec has a scenario for it. This is the change most likely to be felt day one.
- **Moving Dagster storage to Postgres makes Postgres a hard dependency of the Dagster services**, where SQLite made them independent. A Postgres outage now stops the scheduler rather than just the pipelines. → Acceptable: pipelines are useless without the warehouse anyway, and `depends_on: service_healthy` already orders normal startup. Note it does *not* order a restart-policy startup after reboot, which is why the spec's reboot scenario requires eventual convergence rather than ordering.
- **Existing deployments carry a `dagster_home` volume with SQLite storage in it.** Switching the storage block does not migrate old run history; it starts a fresh history in Postgres. → Acceptable for this project — run history is operational, not analytical, and the price data lives in Postgres either way. Worth knowing before it surprises someone.
- **A parsing test asserts intent, not runtime behaviour.** → Accepted, as above; first `docker compose up` on the host is the functional check.
- **`k8s/` drifts further from `docker-compose.yml`.** → Accepted; the manifests are already not the deployment path.

## Migration Plan

1. Land the repo changes. Gate: the CI session set — `uv run pytest`, `uv run mypy src tests`, ruff check and format. Commit `uv.lock` alongside `pyproject.toml`.
2. **Applying to an already-running stack**: `docker compose up -d --build`. Restart policies, logging options and port bindings take effect on container recreation; `dagster.yaml` now does too, via the bind mount.
3. **First deployment on the new host** is the deferred host-setup work, for which this change is a precondition rather than a substitute: it needs `systemctl enable docker` (without it, every guarantee in the container-runtime capability is inert), an `.env` built from the committed `.env.example`, the `pg_dump` restore, and the AH token bootstrap.
4. Rollback is `git revert` plus `docker compose up -d --build`. Nothing here writes data. The one asymmetry: the Dagster storage switch starts a new run history, and reverting returns to the SQLite history as it was, leaving the Postgres-side history stranded but harmless.

## Open Questions

- Whether `mem_limit` per service is needed on a 4 GB VM is deliberately deferred; it depends on observed dbt/dlt peak usage, which nobody has measured yet. It does not affect these specs or the task breakdown.
