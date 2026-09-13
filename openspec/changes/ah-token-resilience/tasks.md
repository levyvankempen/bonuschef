## 1. Credential observability

- [ ] 1.1 Extend `AHTokenManager.adopt()` in `src/bonuschef/utils/ah_auth.py` to report whether the provider returned a refresh credential different from the one used; verify a unit test covering rotated, unrotated and first-adoption cases passes
- [ ] 1.2 Expose the stored credential's age (from the existing `refreshed_at` field) on the manager; verify a test asserts age is computed against an injected clock, not wall time
- [ ] 1.3 Add tests for the rotation and persistence behaviour that already exists but is unspecified — concurrent rotation via `_candidates()`, atomic replace under interruption, and `0600` on the written file; verify all pass with no network

## 2. Heartbeat job

- [ ] 2.1 Add a `token_heartbeat` op-job in `src/bonuschef/dags/defs/jobs/__init__.py` that calls `get_access_token(force_refresh=True)` and nothing else, so the refresh credential is exercised even when the cached access token is still valid; verify a test asserts it forces the refresh rather than accepting a cached token
- [ ] 2.2 Attach rotation and credential age to the run as Dagster metadata; verify a test asserts both are emitted on success
- [ ] 2.3 Let an authentication failure fail the job rather than swallowing it, so the failure sensor sees it; verify a test asserts the job raises when every credential is rejected
- [ ] 2.4 Register the job in `definitions.py`, keeping it out of the asset graph so `AssetSelection.all()` cannot sweep it into `daily_refresh`; verify the existing `test_daily_refresh_includes_bonus_feed_and_all_dbt` still passes unchanged and a new test asserts the job is registered

## 3. Heartbeat schedule

- [ ] 3.1 Add a twice-daily schedule for `token_heartbeat` in `src/bonuschef/dags/defs/schedules/__init__.py` with `DefaultScheduleStatus.RUNNING` and `Europe/Amsterdam`; verify the existing `test_schedules_and_sensors_are_running_on_a_fresh_deployment` covers it and update `test_schedules_run_in_amsterdam_time`'s schedule-name set
- [ ] 3.2 Verify a test asserts the heartbeat schedule's cron is independent of both data schedules — retiming `daily_refresh` must not change it

## 4. Failure alerting

- [ ] 4.1 Add ntfy configuration to `src/bonuschef/config.py` reading `NTFY_TOPIC` and `NTFY_SERVER` (defaulting the server to `https://ntfy.sh`); verify a test asserts the config is absent-not-error when `NTFY_TOPIC` is unset
- [ ] 4.2 Add a `run_failure_sensor` in `src/bonuschef/dags/defs/sensors/__init__.py` that posts pipeline name, run id and failure reason to ntfy; verify a test using the existing `http_post` stub asserts the payload and that it fires once per failed run
- [ ] 4.3 Make the sensor a no-op when `NTFY_TOPIC` is unset, and swallow-and-log delivery errors so a failed notification never fails a run; verify tests cover both, and that no test performs a real network call
- [ ] 4.4 Register the sensor in `definitions.py`; verify `test_sensors_registered` is updated and passes

## 5. Documentation

- [ ] 5.1 Add `NTFY_TOPIC` and `NTFY_SERVER` to `.env.example` with a note that the topic is a capability URL and should be long and random; verify the existing `test_env_example_covers_every_interpolated_variable` still passes and extend the documented-variables test
- [ ] 5.2 Document in `README.md` what the heartbeat is for — that it keeps the refresh credential alive independently of scraping, and that an expired credential still needs one interactive `ah_login`; verify the AH section reads coherently alongside the existing login instructions

## 6. Gate

- [ ] 6.1 Run `uv run pytest` and confirm the full suite passes with no new skips and no network access
- [ ] 6.2 Run `uv run ty check src tests noxfile.py` and confirm it is clean
- [ ] 6.3 Run `uv run ruff check` and `uv run ruff format --diff` over `src tests noxfile.py` and confirm both are clean
