## Why

The stack has only ever run on a developer laptop, started by hand. It is moving to an always-on host, where nothing restarts it after a reboot, nothing bounds the log volume it writes, and its Postgres port and both unauthenticated web UIs publish on every interface. The refresh schedule also still fires at 06:00, a time chosen for a laptop that happened to be awake — and retiming it exposes a run-concurrency problem that the laptop's 06:00 slot happened to hide.

## What Changes

- Every service declares a restart policy, so the stack comes back on its own after a host reboot or a crashed container.
- Every service caps its own log output (`json-file` driver, `max-size` / `max-file`), so unattended running cannot fill the host disk.
- **Every published port binds to the loopback interface only** — Postgres (5455), the Dagster webserver (3000) and the Streamlit portal (8501). Neither UI has any authentication, and the Dagster UI can launch and terminate arbitrary jobs, so none of them should answer on a routable interface. Off-box access goes through Tailscale or an SSH tunnel.
- The `dagster-webserver` and `streamlit` services gain healthchecks, so an unhealthy container is *visible* to an operator or an external monitor. Acting on that signal automatically is deferred — a restart policy reacts to a container exiting, never to its health state.
- `daily_refresh_schedule` moves from `0 6 * * *` to `30 17 * * *`. `markdowns_refresh_schedule` stays at `0 11-20 * * *`.
- **Runs are serialised** (`max_concurrent_runs: 1`). `daily_refresh` rebuilds every dbt model, a strict superset of what `markdowns_refresh` touches, so at 17:30 against an 18:00 clearance run they would race on non-idempotent `on-run-start` DDL and on table-materialisation renames. `daily_refresh_job` also gains the retry policy it currently lacks.
- **`dagster.yaml` is bind-mounted** instead of baked into the image. The `dagster_home` named volume masks the copy the Dockerfile places there, so today a change to that file silently never reaches a running deployment.
- **Dagster's run, event and schedule storage moves to Postgres.** It is currently SQLite on a volume written concurrently by the webserver, the daemon and every run subprocess across two containers.
- A committed `.env.example` documents every key the services read, and the Postgres password comes from the environment instead of being hardcoded in git.
- Unit tests cover each of the above, with no database and no network.

Explicitly **not** in this change, deferred to the host-setup work that follows: VM provisioning, the one-time `pg_dump` data migration, bootstrapping the AH refresh token on the server, monitoring containers (Dozzle, Uptime Kuma), an ntfy failure-alert sensor, acting automatically on an unhealthy container, and per-service memory limits.

## Capabilities

### New Capabilities
- `container-runtime`: how the stack behaves as a long-running deployment — restart behaviour, log retention, which interfaces its published ports answer on, health reporting, and whether a configuration change actually reaches a running deployment.
- `scheduling`: when each pipeline runs unattended, in which timezone, whether it is enabled on a fresh deployment, and whether two runs may execute at once.

### Modified Capabilities
<!-- None: the project had no specs before this change; both capabilities above are new. -->

## Impact

- `docker-compose.yml` — every service block. Three port mappings change from all-interfaces to loopback; anything currently reaching 5455, 3000 or 8501 across the LAN stops working and must tunnel.
- `dagster.yaml` — gains a run-coordinator concurrency limit and a Postgres storage block; becomes a bind-mounted file rather than an image artifact.
- `src/bonuschef/dags/defs/schedules/__init__.py` — one cron string.
- `src/bonuschef/dags/defs/jobs/__init__.py` — a retry policy on `daily_refresh_job`.
- `pyproject.toml` / `uv.lock` — `pyyaml` and `types-PyYAML` become declared dev dependencies.
- `.env.example` — new, committed; `README.md` — the new schedule time and the loopback binding.
- `tests/unit/test_definitions.py` — the existing `test_schedules_run_in_amsterdam_time` asserts the old `0 6 * * *`; a new `tests/unit/test_compose_config.py` covers the deployment guarantees.
- No application code, no database schema, and no dbt model is touched. `k8s/` is untouched and drifts further from Compose; it is not the deployment path.
