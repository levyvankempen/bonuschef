## 1. Credential age and rotation

- [x] 1.1 Add `refresh_token_issued_at: float = 0.0` to `TokenBundle` in `src/bonuschef/utils/ah_auth.py` (last position, with a default — the suite constructs `TokenBundle` positionally) plus a `credential_age_s(now)` returning `None` when it is `0.0`; have `TokenStore.load()` read it via `raw.get("refresh_token_issued_at", 0)` like the existing `refreshed_at`; verify a test asserts a token file written without the field still loads and reports age as unknown
- [x] 1.2 In `adopt()`, stamp `refresh_token_issued_at` only when the refresh credential value differs from the one already on disk, carrying the previous value forward otherwise, so age measures how long *this* credential has survived; verify tests cover carried-forward, newly-rotated and unknown-start cases against an injected clock
- [x] 1.3 Add a `RefreshOutcome` dataclass (bundle, `rotated`, `credential_age_s`, `used_fallback`) and change the private `_refresh_and_store` to return it, computing `rotated` against the credential actually used and `used_fallback` from the candidate index — not against what was on disk, which would report a `.env` fallback as a rotation; keep `adopt()`'s public signature and return type unchanged so `ah_login.py:89` and its two tests are untouched; verify `test_picks_up_token_rotated_by_another_process` is updated to `.bundle.access_token` and passes
- [x] 1.4 Add a public `refresh_now()` returning `RefreshOutcome`, and a `manager_from_env()` factory building the manager from the token file and `.env` bootstrap; verify a test asserts `refresh_now()` always calls the refresher even when the cached access token is still fresh
- [x] 1.5 Log at WARNING when the token file exists but fails to parse, instead of returning `None` silently — a corrupt file is currently indistinguishable from a missing one, which strands the deployment if `AH_REFRESH_TOKEN` has been cleared; verify a test asserts the warning and that behaviour is otherwise unchanged
- [x] 1.6 Add the one genuinely missing persistence test: monkeypatch `json.dump` to raise mid-save, then assert the original file is byte-identical and no `.ah_tokens-*` temp file remains. Do NOT re-add `0600` or concurrent-rotation tests — `test_round_trip_and_private_permissions` and `test_picks_up_token_rotated_by_another_process` already cover those

## 2. Heartbeat job

- [x] 2.1 Add a `refresh_ah_credential` op and `token_heartbeat_job` in `src/bonuschef/dags/defs/jobs/__init__.py` calling `refresh_now()`, importing the factory from `ah_auth` rather than from the markdowns asset module (which imports `dlt` at module scope, and which `schedules`/`sensors` both import); verify a test asserts the job runs and exercises the refresh
- [x] 2.2 Emit `AssetObservation(asset_key="ah_refresh_credential", ...)` via `context.log_event` carrying `rotated`, `used_env_fallback` and `credential_age_days`, plus a log line for the compute logs; verify a test asserts the observation metadata using `execute_in_process` and `get_asset_observation_events`
- [x] 2.3 Let an authentication failure propagate and fail the run rather than being caught, so the failure sensor sees a real `RUN_FAILURE`; verify a test asserts the job fails when every credential is rejected
- [x] 2.4 Give the job `op_retry_policy=RetryPolicy(max_retries=2, delay=60)`, required by the already-synced `scheduling` requirement that every scheduled pipeline retries; verify `test_scheduled_jobs_retry_transient_failures` covers it — and widen that test from its hardcoded job tuple to "every job a schedule targets", so the next scheduled job cannot reopen this gap
- [x] 2.5 Register the job in `definitions.py` and add `"token_heartbeat"` to the existing exact-set assertion in `test_all_jobs_registered`; do not add a second registration test, and do not write a test guarding against `AssetSelection.all()` sweeping it up — an op-job is structurally invisible to asset selection

## 3. Heartbeat schedule

- [x] 3.1 Add a twice-daily schedule at `30 3,15 * * *` Europe/Amsterdam with `DefaultScheduleStatus.RUNNING`, avoiding the `:00` clearance scrapes, the 17:30 rebuild, and the 02:00–03:00 window that does not exist on the spring-forward day; verify `test_schedules_run_in_amsterdam_time`'s name set and cron assertions are updated
- [x] 3.2 Add a test pinning the design decision that the refresh cadence outpaces credential lifetime: assert the heartbeat interval times two is less than `MAX_ACCESS_TOKEN_AGE_S`, so one missed cycle still leaves margin

## 4. Failure alerting

- [x] 4.1 Add `NtfyConfig` to `src/bonuschef/config.py` with `topic`, `server` (default `https://ntfy.sh`), a `url` property and `from_env()` returning `None` when `NTFY_TOPIC` is unset or empty — a deliberate divergence from the house pattern of raising, because absent alerting is a choice rather than an error; keep `__post_init__` validation for direct construction; verify a test asserts `from_env() is None` when unset and that a malformed server still raises
- [x] 4.2 Add a `run_failure_sensor` in `src/bonuschef/dags/defs/sensors/__init__.py` with `default_status=DefaultSensorStatus.RUNNING`, posting job name, run id and failure reason to ntfy with an explicit `timeout`; take the reason from `context.get_step_failure_events()` and `error.message` — `context.failure_event.message` carries only "Steps failed: [...]" and would ship a useless alert — truncating the posted text and never including a config repr
- [x] 4.3 Make the sensor a no-op when unconfigured and swallow-and-log delivery errors, which is required rather than polite: a raising sensor leaves the daemon's cursor uncommitted and the same failure is re-notified on the next tick; add `NTFY_TOPIC` and `NTFY_SERVER` to `_ISOLATED_VARS` in `tests/conftest.py`, without which a developer or CI runner with the variable exported would post to ntfy for real; verify tests cover both paths and that no test performs a network call
- [x] 4.4 Verify a success event produces no notification, using `build_run_status_sensor_context` with `get_run_success_event()` and asserting the `http_post` stub recorded nothing. Do not attempt to verify "once per failed run" by direct invocation — that is true by construction and the real property lives in the daemon cursor
- [x] 4.5 Register the sensor in `definitions.py`; verify `test_sensors_registered` is updated and that `test_schedules_and_sensors_are_running_on_a_fresh_deployment` covers its default status

## 5. Instance configuration

- [x] 5.1 Add `run_monitoring` with `max_runtime_seconds` to `dagster.yaml` so a wedged run cannot hold the single run slot indefinitely and starve the heartbeat into a permanently `QUEUED` state that emits no failure event; verify a test asserts the block exists and that `max_concurrent_runs` is still 1
- [x] 5.2 Add a comment in `dagster.yaml` stating that `run_retries` must stay unset, because run-level retries emit one `RUN_FAILURE` per attempt and would break the one-notification-per-failure requirement; verify a test asserts no `run_retries` block is configured

## 6. Documentation

- [x] 6.1 Add `NTFY_TOPIC=` (deliberately empty, so a copied template cannot post to a guessable public topic) and `NTFY_SERVER` to `.env.example` with a note that the topic is a capability URL and must be long and random; verify by extending the hardcoded tuple in `test_env_example_documents_the_variables_the_services_read` — note `test_env_example_covers_every_interpolated_variable` will NOT catch this, since these are `env_file` keys and never interpolated
- [x] 6.2 Document in `README.md` what the heartbeat is for, that alerting covers pipeline failure but not the host being off, and correct the claim that `AH_REFRESH_TOKEN` in `.env` is a durable fallback — with three forced refreshes a day it goes stale within hours if AH rotates, leaving the token file on the volume as the sole credential; verify the AH section reads coherently with the existing login instructions

## 7. Gate

- [x] 7.1 Run `uv run pytest` and confirm the full suite passes with no new skips and no network access
- [x] 7.2 Run `uv run ty check src tests noxfile.py` and confirm it is clean
- [x] 7.3 Run `uv run ruff check` and `uv run ruff format --diff` over `src tests noxfile.py` and confirm both are clean
