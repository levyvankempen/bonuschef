## 1. Dependencies and test scaffolding

- [x] 1.1 Add `pyyaml` and `types-PyYAML` to `[dependency-groups].dev` in `pyproject.toml`, next to the existing `types-requests`; verify `uv sync --dev` succeeds, `uv run python -c "import yaml"` exits 0, and `uv run mypy src tests` stays clean once a `yaml` import exists (without the stubs it fails `import-untyped`, which `ignore_missing_imports` does not suppress)
- [x] 1.2 Commit the regenerated `uv.lock` in the same change; verify `git status` shows it staged and `uv sync --frozen` succeeds (the Dockerfile uses `--frozen`, which builds from a stale lock rather than erroring)
- [x] 1.3 Create `tests/unit/test_compose_config.py` with a module-scoped fixture resolving the repo root via `Path(__file__).resolve().parents[2]` (house style, as in `test_definitions.py`) and loading `docker-compose.yml` with `yaml.safe_load`; verify a first assertion that the four known services are present passes

## 2. Compose runtime hardening

- [x] 2.1 Add `restart: unless-stopped` to all four services; verify a test iterating every entry of `services` asserts each has it
- [x] 2.2 Add `logging: {driver: json-file, options: {max-size: 10m, max-file: "3"}}` to all four services; verify a test iterating every service asserts the driver and both options
- [x] 2.3 Bind every published port to loopback — `127.0.0.1:5455:5432`, `127.0.0.1:3000:3000`, `127.0.0.1:8501:8501`; verify a test parsing every published mapping across all services asserts each is prefixed `127.0.0.1:`
- [x] 2.4 Add an exec-form healthcheck to `dagster-webserver` — `test: [CMD, python, -c, 'import urllib.request,sys; sys.exit(0 if urllib.request.urlopen("http://127.0.0.1:3000/server_info", timeout=5).status == 200 else 1)']` with `interval: 30s`, `timeout: 10s`, `retries: 3`, `start_period: 60s`; add a comment saying `uv run` must NOT be added to the probe (it re-resolves the env and locks `.venv` every 30s, and may reach the network); verify a test asserts the service defines a healthcheck referencing that path
- [x] 2.5 Add the same exec-form healthcheck to `streamlit` against `http://127.0.0.1:8501/_stcore/health` with `start_period: 30s`; verify a test asserts both web services carry a healthcheck — do NOT assert that `dagster-daemon` lacks one
- [x] 2.6 Change `POSTGRES_PASSWORD: postgres` to `${POSTGRES_PASSWORD:?}` so startup fails loudly on a missing secret; verify a test asserts no service declares a literal `postgres` password, and `docker compose config -q` errors when the variable is unset
- [x] 2.7 Bind-mount `dagster.yaml` read-only on both Dagster services — `- ./dagster.yaml:/app/dagster_home/dagster.yaml:ro`; verify a test asserts both services carry that mount (without it the `dagster_home` named volume masks the file and every task in section 3 silently never applies)
- [x] 2.8 Verify the file still parses: `docker compose config -q` exits 0 with a populated `.env` present (manual check — client-side parse, no daemon needed; not part of the pytest suite)

## 3. Dagster instance configuration

- [x] 3.1 Add `run_coordinator.config.max_concurrent_runs: 1` to `dagster.yaml`; verify a test loads `dagster.yaml` and asserts the limit is exactly 1 (Dagster's default is 10, so the collision is live until this lands)
- [x] 3.2 Add a `storage:` block to `dagster.yaml` pointing run, event-log and schedule storage at the existing Postgres service, reading host/port/credentials from the environment already passed to both Dagster services; verify a test asserts a `storage` block exists and references no SQLite path
- [x] 3.3 Verify sections 3.1 and 3.2 are reachable at runtime by confirming task 2.7's bind mount is in place first — these two are ordered after it, not independent of it

## 4. Schedules and jobs

- [x] 4.1 Change `daily_refresh_schedule.cron_schedule` in `src/bonuschef/dags/defs/schedules/__init__.py` from `"0 6 * * *"` to `"30 17 * * *"`, updating the inline comment; leave `markdowns_refresh_schedule` at `"0 11-20 * * *"`
- [x] 4.2 Update `test_schedules_run_in_amsterdam_time` in `tests/unit/test_definitions.py` to assert `"30 17 * * *"`, keeping the existing `markdowns_refresh_schedule` and `Europe/Amsterdam` assertions; verify with `uv run pytest tests/unit/test_definitions.py`
- [x] 4.3 Add an `op_retry_policy=RetryPolicy(max_retries=2, delay=120)` to `daily_refresh_job` in `src/bonuschef/dags/defs/jobs/__init__.py`, matching the policy `markdowns_refresh_job` already has; verify a test asserts both jobs carry a retry policy
- [x] 4.4 Add a test asserting both schedules AND both sensors are registered with `RUNNING` default status, so a fresh host with empty scheduler state starts working unattended; verify it passes

## 5. Deployment documentation

- [x] 5.1 Create a committed `.env.example` listing every key the compose services read (the Postgres `DESTINATION__*` and `PG_*` sets, `ENVIRONMENT`, `TARGET_SCHEMA`, the `GITHUB_*` set, `AH_STORE_ID`, `AH_REFRESH_TOKEN`, and the new `POSTGRES_PASSWORD`) with placeholder values and no real secrets; verify a test asserts every `${VAR}` referenced in `docker-compose.yml` appears in `.env.example`
- [x] 5.2 Add to `README.md`: the 17:30 Amsterdam daily-refresh time (currently documented nowhere), and a note that all three ports now publish on `127.0.0.1` only so off-box clients need Tailscale or `ssh -L`; verify by reading the scheduling paragraph near the existing hourly-clearance line. Do NOT strip the existing `5455` references at lines 65, 71 and 149 — the port number is unchanged, only the bind interface, and those lines stay correct
- [x] 5.3 Add a README pointer to `.env.example` in the setup section; verify the documented first-run sequence (clone, copy `.env.example` to `.env`, fill it, `docker compose up -d --build`) is complete and in order

## 6. Gate

- [x] 6.1 Run `uv run pytest` and confirm the full suite passes with no new skips
- [x] 6.2 Run `uv run mypy src tests` and confirm it is clean
- [x] 6.3 Run `uv run ruff check src tests noxfile.py` and `uv run ruff format --diff src tests noxfile.py` and confirm both are clean
