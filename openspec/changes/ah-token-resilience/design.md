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

**Rotation observability goes in `adopt()`, emitted as run metadata.**
`adopt()` is the one place that sees both the credential used and the one returned, so the comparison is free there. It returns the bundle already; the heartbeat job reads `refreshed_at` off the stored bundle for age and attaches both facts as Dagster run metadata, which is queryable later without adding a table. Rejected: a dedicated `token_events` table — more schema for a question that should be answered within weeks and then stop mattering.

**Alerting is a `run_failure_sensor` posting to ntfy over `requests`.**
`run_failure_sensor` fires once per failed run *after* retries are exhausted, which is exactly the "one notification, not one per attempt" requirement — Dagster's retry mechanism does not mark the run failed until the policy is spent. ntfy needs no account and no SDK: a `POST` with a text body. Configuration through `NTFY_TOPIC` / `NTFY_SERVER` with the sensor skipping when unset keeps the suite offline by construction. Delivery errors are caught and logged, never re-raised — an alerting failure that fails a run would be worse than no alerting.

**The heartbeat is not exempted from run serialisation.**
`max_concurrent_runs: 1` applies to it too. It is one HTTP call, so queueing behind a long rebuild costs nothing real, and exempting it would mean per-tag concurrency rules for no benefit.

## Risks / Trade-offs

- **The heartbeat masks a scraping failure from the token's perspective.** If clearance scraping is broken for a month, the credentials stay alive and nothing forces the operator to notice — precisely the intent, but it means the *scrape* failure must be caught by the alerting rather than by the eventual token death. → That is what `failure-alerting` is for, and it is in this same change for that reason.
- **ntfy topics are unauthenticated and world-readable if the name is guessed.** The notification names pipelines and error text, which can carry store ids or product names. → Use a long random topic name; it is a capability URL. Do not put credentials in alert bodies.
- **The evidence gathered may show AH expires refresh credentials absolutely.** Then the heartbeat reduces, but does not remove, manual logins. → The alerting still turns a silent two-month failure into a same-day one, so the change is worthwhile either way. This is the outcome the instrumentation exists to detect.
- **`force_refresh=True` twice daily means more refresh calls than strictly needed**, and if AH rotates on every refresh, more rotation. → Rotation is already handled atomically and a rotated credential invalidating its predecessor is the normal contract; the alternative leaves the credential unexercised, which is the failure we are fixing.

## Migration Plan

1. Land the repo changes; the CI session set is the gate.
2. An interactive login is still required *once* to recover from the current expired state — this change does not repair an already-dead credential, it prevents the next one.
3. Set `NTFY_TOPIC` in `.env` on the host and subscribe the phone app to it. With it unset, everything else still works and alerting is simply inert.
4. Rollback is `git revert`; nothing here writes durable state beyond the token file, whose format is unchanged.

## Open Questions

- How long an AH refresh credential survives when exercised continuously is unknown, and deliberately so — the instrumentation in this change is what answers it. It does not affect the specs or the task breakdown; it affects only whether a *later* change is needed.
