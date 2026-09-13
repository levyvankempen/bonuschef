## Why

The AH member refresh token expired twice — issued 2026-07-06, dead by 2026-09-13 — and both times the cause was the same: nothing used it. Access tokens are capped at 24h, so any day a scrape runs the refresh token is exercised and survives; when the stack sits idle it is never called and AH invalidates it. Recovery needs an interactive browser login that cannot be automated (the login page runs invisible hCaptcha), so every expiry costs manual work.

Two structural problems make that worse. The clearance scrape is the *only* caller of the token manager in the entire codebase, so any unrelated scraping failure silently stops token refresh too — turning a recoverable outage into one that needs a human at a browser. And nothing reports failure, so the last expiry went unnoticed for two months.

## What Changes

- **A token heartbeat**: a scheduled job whose only work is to obtain a valid access token. Token liveness stops depending on whether scraping succeeds.
- **Rotation and age become observable**: each refresh records whether AH returned a *new* refresh token and how old the stored one is. This settles a question open since July — whether AH's refresh token expiry is sliding (extends on use) or absolute (a fixed maximum life regardless of use). If it turns out to be absolute, no amount of heartbeating avoids periodic re-auth, and we need to know that rather than assume.
- **Failure alerting**: a run-failure sensor pushes to ntfy so a dead token is known within the hour instead of at the next time someone opens the portal.

Note on scope: alerting was previously deferred as "container-side". That reasoning does not hold — a Dagster `run_failure_sensor` is application code in this repo. The container-side monitoring (Dozzle, Uptime Kuma) stays deferred.

## Capabilities

### New Capabilities
- `ah-authentication`: how member access to the AH API is kept alive without operator action — token persistence, rotation, liveness independent of any one consumer, and the observability needed to tell an expiring token from a broken one.
- `failure-alerting`: how an unattended pipeline failure reaches a human.

### Modified Capabilities
- `scheduling`: adds the heartbeat to the set of scheduled pipelines, and states that it must keep running when other pipelines are failing.

## Impact

- `src/bonuschef/utils/ah_auth.py` — `adopt()` gains rotation detection; the manager exposes stored-token age.
- `src/bonuschef/dags/defs/jobs/` and `schedules/` — a new heartbeat job and schedule.
- `src/bonuschef/dags/defs/sensors/` — a new run-failure sensor.
- `src/bonuschef/config.py` — ntfy configuration, read from the environment.
- `.env.example`, `README.md` — the new ntfy variables and what the heartbeat is for.
- `tests/unit/` — coverage for rotation handling, heartbeat behaviour and alert dispatch, all stubbed; no network.
- **Not affected**: the interactive login flow itself, which still requires a human and a browser.
