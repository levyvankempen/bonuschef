## Context

See `proposal.md` — Why. What the code already does, and where the gaps are:

- `AHTokenManager.adopt()` already persists `tokens.get("refresh_token") or refresh_token_used`, so **rotation is handled**. `_candidates()` already re-reads from disk to survive a concurrent rotation, and `TokenStore.save()` is already an atomic `mkstemp` + `os.replace` at `0600`. Several requirements in `specs/ah-authentication/` therefore describe existing behaviour and need tests, not new code.
- `default_token_file()` resolves to `$DAGSTER_HOME/ah_tokens.json`, which is the shared `dagster_home` volume. Persistence across rebuilds already works.
- The gap is liveness: `grep` finds exactly one caller of the token manager outside `ah_auth.py` itself — `dlt/ah_markdowns/__init__.py:55`. Nothing else ever refreshes.
- `MAX_ACCESS_TOKEN_AGE_S` is 24h and `EXPIRY_MARGIN_S` is 5 minutes, so a daily call is the minimum that keeps a token continuously refreshed.
- The repo has no outbound-notification code and no HTTP client beyond `requests`, which is already a dependency.

## Goals / Non-Goals

**Goals:**

- Decouple credential liveness from the success of any data pipeline.
- Answer the sliding-vs-absolute expiry question with recorded evidence rather than assumption.
- Make a failure that needs human recovery visible within an hour.

**Non-Goals:**

- Automating the interactive login. The AH login page runs invisible hCaptcha (`captchaType: "HINVISIBLE"`, observed in the page payload), which exists specifically to defeat scripted login. A Playwright-driven login would also mean storing AH account credentials on the host. Revisit only if the evidence gathered here shows AH forces re-auth on a fixed clock.
- Container-side monitoring (Dozzle, Uptime Kuma) — still deferred, genuinely host concerns.
- Alerting on anything other than run failure. Freshness and volume checks are a separate concern.

## Decisions

**The heartbeat is its own job and schedule, not an asset.**
It materialises nothing and has no lineage; modelling it as an asset would put a node in the graph that no downstream model consumes and that `AssetSelection.all()` would sweep into `daily_refresh`. A plain op-job keeps it out of the asset graph entirely. Alternative rejected: a sensor — sensors are for reacting to external state, and this is a fixed cadence.

**Cadence is every 12 hours, not daily.**
The access token is capped at 24h, so daily is the bare minimum and a single missed cycle would leave a gap. Twice daily gives one free failure before anything is at risk, and the call costs one HTTP round trip.

**The heartbeat forces a refresh rather than accepting a cached token.**
`get_access_token()` returns the stored token untouched when it is still fresh, which would make the heartbeat a no-op exactly when the access token is valid but the *refresh* token is going stale — the failure we are fixing. It calls with `force_refresh=True` so the refresh credential is genuinely exercised every cycle.

**Credential age needs a new persisted field; `refreshed_at` is the wrong quantity.**
`adopt()` stamps `refreshed_at = now` on every adoption, so `now - refreshed_at` is always one heartbeat interval — a constant, forever. The question this change exists to answer is how long a *credential value* survives while being exercised, so `TokenBundle` gains `refresh_token_issued_at`, stamped only when the refresh token value actually changes and carried forward untouched otherwise. It goes last with a default of `0.0` because `TokenBundle` is constructed positionally throughout the test suite, and `TokenStore.load()` reads it with `raw.get(..., 0)` exactly as it already does for `refreshed_at`, so the live token file on the volume keeps loading. `0.0` means *unknown* and reports as unknown rather than guessing a start date that would understate the age.

**Rotation detection goes in `_refresh_and_store`, not `adopt()`.**
`_refresh_and_store` already holds both facts: the previous bundle (for age) and the loop variable naming the credential actually used (for rotation). Comparing there keeps `adopt()` as pure persistence, and avoids two bugs that an `adopt()`-based comparison would introduce. First, `ah_login.py` calls `adopt(tokens)` with `refresh_token_used=""`, so `returned != used` is trivially true and every interactive login would be recorded as "AH rotated" — poisoning the evidence. Second, `_candidates()` may fall back from the stored credential to the `.env` bootstrap, and comparing against what was on disk would report a fallback as a rotation. `adopt()`'s public signature and return type are therefore unchanged, which also leaves `ah_login.py` and its two existing tests untouched.

**The heartbeat calls a new `refresh_now()`, not `get_access_token()`.**
`get_access_token()` returns a bare `str` and discards the bundle, so a heartbeat built on it could not report rotation or age at all. `refresh_now()` returns a `RefreshOutcome` carrying the bundle, `rotated`, `credential_age_s` and `used_fallback`. `get_access_token(force_refresh=True)` keeps working unchanged for the scrape path.

**Observations, not "run metadata" — which is not an API.**
`OpExecutionContext` in 1.11.16 has no `add_run_metadata`. Of what exists, `add_output_metadata` lands on a per-run event with no index (readable only by opening 60 runs one at a time) and `context.log` writes to compute-log files that never reach Postgres. `context.log_event(AssetObservation(asset_key="ah_refresh_credential", metadata={...}))` is indexed by asset key, retrievable in aggregate via `instance.fetch_observations(...)`, and plots numeric metadata as a time series on the asset's page — which is literally "the greatest age a credential reached while still working", read off a chart. A run tag was considered as a filterable extra and not implemented — the observation is the durable record and a second, weaker copy of the same fact is not worth the line. Caveat: an observation does register the key in the asset catalog as an unmanaged asset, so it appears in the UI; it still cannot enter `defs.resolve_asset_graph()` and so cannot be swept into `daily_refresh` by `AssetSelection.all()`.

**The heartbeat gets an op-level retry policy.**
The already-synced `scheduling` capability requires that *every* scheduled pipeline retries before giving up, and a transient AH 5xx or DNS blip is exactly what that is for. The counter-argument — that a dead credential is not transient and retrying delays the alert — costs two minutes against a failure discovered in hours, which is not a trade worth making. Op-level retry matters for a second reason: retries happen *inside* the run, so exactly one `RUN_FAILURE` is emitted and the "one notification, not one per attempt" requirement holds. Run-level retries (`run_retries` in `dagster.yaml` plus the `dagster/max_retries` tag) would emit one per attempt and must stay unset; `dagster.yaml` carries a comment saying so.

**The heartbeat is not exempted from run serialisation, but a wedged run is bounded.**
`max_concurrent_runs: 1` applies to the heartbeat too, and there is no exemption from the global cap — `tag_concurrency_limits` can only restrict further. Queueing behind a *slow* run costs nothing real. Queueing behind a *wedged* one is a genuine hole: a `dbt` run blocked on a Postgres lock holds the single slot indefinitely, every heartbeat sits in `QUEUED`, the credential is never exercised, and because a `QUEUED` run never emits `RUN_FAILURE` the alerting stays silent — the original failure mode, now behind a monitor that reports nothing. `run_monitoring` with `max_runtime_seconds` (available in 1.11.16, verified) bounds this by killing a run that overruns, which drains the queue and produces a real failure the sensor can report. A `dagster/priority` tag additionally puts the heartbeat at the front of the queue.

## Risks / Trade-offs

- **The heartbeat masks a scraping failure from the token's perspective.** If clearance scraping is broken for a month, the credentials stay alive and nothing forces the operator to notice — precisely the intent, but it means the *scrape* failure must be caught by the alerting rather than by the eventual token death. → That is what `failure-alerting` is for, and it is in this same change for that reason.
- **ntfy topics are unauthenticated and world-readable if the name is guessed.** The notification names pipelines and error text, which can carry store ids or product names. → Use a long random topic name; it is a capability URL. Do not put credentials in alert bodies.
- **Run-failure alerting covers failure, not absence.** If the stack is down or the daemon is not running, no run fails, no sensor evaluates, and nothing is sent — so the alerting does not cover the "host was off" case, only "host up, pipeline broken". `restart: unless-stopped` makes the former unlikely but not impossible. → Stated rather than papered over; a dead-man's-switch ping belongs with the deferred container-side monitoring, where an external service is doing the watching.
- **The evidence gathered may show AH expires refresh credentials absolutely.** Then the heartbeat reduces, but does not remove, manual logins. → The alerting still turns a silent two-month failure into a same-day one, so the change is worthwhile either way. This is the outcome the instrumentation exists to detect.
- **`force_refresh=True` twice daily means more refresh calls than strictly needed**, and if AH rotates on every refresh, more rotation. → Rotation is already handled atomically and a rotated credential invalidating its predecessor is the normal contract; the alternative leaves the credential unexercised, which is the failure we are fixing.

## Migration Plan

1. Land the repo changes; the CI session set is the gate.
2. An interactive login is still required *once* to recover from the current expired state — this change does not repair an already-dead credential, it prevents the next one.
3. Set `NTFY_TOPIC` in `.env` on the host and subscribe the phone app to it. With it unset, everything else still works and alerting is simply inert.
4. Rollback is `git revert`; nothing here writes durable state beyond the token file, whose format is unchanged.

## Open Questions

- How long an AH refresh credential survives when exercised continuously is unknown, and deliberately so — the instrumentation in this change is what answers it. It does not affect the specs or the task breakdown; it affects only whether a *later* change is needed.
