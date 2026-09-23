# Design

## The unknown, now measured

**Clearance is store-scoped and authentication-gated. It does not vary by
member.** One credential reads any store's clearance.

Measured on 2026-09-20 with the operator's live credential, against real
store ids taken from ah.nl/winkels:

    1876  own store                     90 items
    1266  Driebergen, Binnenhof        217 items
    1177  Doorn, Dorpsstraat           183 items
    8758  Zeist, Hoog Kanje            242 items
    5557  Driebergen, Hoofdstraat 129    0 items

The contents differ per store, so this is not one store's answer repeated.
5557 returning nothing is a real answer too - a store can legitimately have no
clearance - which matters for the portal: an empty list is not a failure.

**This removes the reason for per-user Albert Heijn credentials.** The first
draft justified them by claiming a shared session would give a friend
clearance that is really the operator's. It would not. A single credential
fetching each distinct store is correct for everybody.

What that deletes: storing other people's supermarket sessions, and with them
the encryption-at-rest scheme, the key-rotation story, the revocation UI, the
per-account heartbeat fan-out, and the connect flow that required a friend to
copy an authorization code out of desktop DevTools behind hCaptcha - which was
the single thing most limiting who could be invited.

What remains true: the clearance grain stays `[store_id, webshop_id]`, and
the six `unique_combination_of_columns` tests that an account dimension would
have broken are untouched.

What is given up, honestly: every store is fetched by one account, so the
request load and any consequence of it concentrates there. At four stores
that is four requests an hour against one that exists today. If that ever
becomes a problem, per-user credentials return as an optimisation with a
measured reason, rather than as an assumption.

## Authentication, and the part Streamlit makes ugly

Streamlit 1.50 **cannot set a cookie**. `st.context.cookies` is read-only and
is populated from the websocket upgrade request, so a cookie written by any
other means is invisible until the next full page load - not the next rerun.

That leaves three ways to hold a session, and the choice must be recorded
rather than discovered:

1. **`st.query_params`** - survives reload and restart, validated against
   Postgres each run. The token sits in the URL bar, in history, and leaks
   via `Referer` to any `st.link_button` that points at ah.nl.
2. **A cookie component** (`extra-streamlit-components`) - correct, a new
   JavaScript dependency, and its first read returns `None`, which produces
   the flicker-then-login rerun.
3. **Identity from the tailnet.** Friends join the tailnet anyway.
   `tailscale serve` injects an identity header, and Streamlit 1.50 has
   `server.trustedUserHeaders` to read it into `st.user`. No password, no
   hash, no throttle, no session table - it deletes most of section 2. Its
   security precondition is that Streamlit stays bound to loopback so nothing
   but the proxy can set the header, which compose already guarantees and
   `test_compose_config.py` already enforces.

**Decided: the cookie component.** Not the tailnet identity, though it is
cheaper and would have deleted most of section 2. The reasoning for rejecting
it is the right one: friends on a tailnet is a stopgap for a system meant to
reach people who are not on it, and building auth around an identity source
that disappears the moment the app is public means writing section 2 twice.
The cookie is what the eventual shape needs, so it is what gets built.

Not the URL token either: it survives reload, costs nothing, and puts a live
session token into browser history and into the `Referer` of every link to
ah.nl on the page. Acceptable for a tailnet alpha, not for the thing this is
building towards, and the whole point of the decision above is not to build
for the stopgap.

The cost is honest: a JavaScript dependency, and a first read that returns
`None` and forces a rerun, which is the flicker-then-login every Streamlit
auth implementation has.

Whichever is chosen, the session record lives in Postgres - a restart must not
sign everybody out - and idle expiry is enforced against that row on each
rerun, not against the cookie, because Streamlit reads cookies only at connect.

**The gate goes in `app.py` above `st.navigation`, ending in `st.stop()`.**
That makes "a page cannot be added unguarded" structural rather than a
convention: `pg.run()` is the only thing that executes a page function and it
is unreachable when the script already stopped. The account is passed into
page functions as an argument, not held in a module global, because the test
harness already forwards arguments and a global would force tests into module
state.

## Passwords, if passwords are chosen

No password library is present. `argon2-cffi`, `bcrypt` and `passlib` are all
absent; `cryptography` 46 is in the image already, via
`dagster-dg-cli -> dagster-cloud-cli -> github3-py -> pyjwt[crypto]`.

Use `cryptography`'s `Scrypt` at `n=2**15, r=8, p=1`, 16-byte salt, stored
with its parameters so they can be raised later. Not `hashlib.scrypt`: OpenSSL
caps memory at 32 MB by default and those parameters raise `ValueError`, which
turns "raise the cost" into a production crash or a silent drop to `n=2**14`.

The slow-hash-in-a-fast-suite tension is solved the way Django solves it: make
the cost a parameter, monkeypatch it down in an autouse fixture, and assert the
*production constant* separately in a test that does no hashing at all. That
assertion is the one that protects the requirement; a round-trip test does not.

## Credential encryption

`AESGCM` from `cryptography`, 32 random bytes in `.env` beside the secrets
already there, fresh nonce per encryption, and **`account_id` as the
associated data** - which binds a ciphertext to its row, so pasting one
account's credential into another's fails to decrypt instead of quietly
working. `key_id` on the row so rotation is possible.

Key loss means every friend reconnects their AH account by hand. Nothing else
is lost. That is a one-line consequence with a large operational tail, given
what connecting costs.

Two existing surfaces need auditing: `AHAuthError` carries `resp.text[:200]`
of a failed refresh, and `ah_login.py` prints the refresh token to stdout by
design - correct for an operator bootstrapping their own account, wrong if
reused for a friend. `TokenBundle` is a plain dataclass, so its generated
`__repr__` puts the token into any traceback.

## Data model

Three shapes, not two:

1. **Shared catalogue** - recipes, ingredient lines, and the concept-to-
   product resolutions. The ~1,900 resolutions are facts about the catalogue,
   each having cost an AH search; scoping them per account gives every friend
   an unpriceable collection. This is also why the existing requirements about
   correcting a match applying "to every recipe using that ingredient" survive
   unchanged.
2. **Per-account annotations** - saved, last made, notes, ingredient
   overrides, **and verdicts**. Today `int_pool_recipes_available` excludes
   any recipe anybody adopted or rejected, so one person's "niet voor mij"
   hides it from all four.
3. **Per-account secrets** - password hash or identity, store, credential.

## Overrides, and where the boundary goes

Overrides on read must mean *in dbt*, not in the portal. Getting from an
ingredient line to a cost involves candidate explosion, cheapest-priced
selection with `DISTINCT ON` and NULL-last ordering, multibuy exclusion, the
stale-reference rule, the `LEAST(price_ordinary, offer_price)` guard and the
clearance stock claim. `fct_recipe_cost_breakdown_bonus` carries a comment
about what happened last time that logic was recomputed elsewhere: two marts
gave two different answers for the same offer.

So the boundary is what matters, and it is a spec constraint rather than an
implementation detail:

**Overrides apply to saved recipes only, never to the pool.** The shared
pipeline keeps its `(store_id, recipe_id, item_key)` grain. A narrow overlay
covers only the `(account, recipe)` pairs that actually have an override.
`fct_recipe_cost_latest` and `fct_recipe_cost_breakdown` gain `account_id` and
LEFT JOIN it. At four users that is roughly 360 extra rows; putting the
account dimension on the pool instead would be roughly 336,000, for nothing,
since store and account are one-to-one anyway.

`fct_recipe_cost_history` deliberately keeps its catalogue grain. Rewriting
years of history because somebody halved the garlic is worse than not having
per-account history.

An edited line that resolves to nothing has no representable shape today: the
model asserts a line is either a pinned product or a resolved concept. A third
`source_kind` is needed, or the spec's "the edit is kept and shown as
unresolved" and the shape test are mutually unsatisfiable.

## Ingestion

**Loop over stores inside the existing asset. Not partitions.**

`max_concurrent_runs: 1` is deliberate and documented - dbt's on-run-start DDL
is not safe twice at once. The downstream rebuild is inherently all-stores, so
partitioned ingestion either rebuilds the warehouse N times an hour or needs a
separate unpartitioned job, which splits the single run the "Refresh now"
button waits on. And 35 of that job's 39 seconds is process startup, which
partitioning pays N times on a 2 GB box.

A per-store `AHAuthError` is caught and recorded as asset metadata; the asset
fails only when every credential is rejected. Otherwise one friend's dead
token pages the operator hourly, which is the opposite of the requirement.

The same applies to the token heartbeat, which calls `manager_from_env()` -
one credential. Four friends' tokens will expire from disuse exactly as the
operator's has, twice.

## Migrations

There is no migration tooling. The `alembic_version` table in Postgres is
**Dagster's**, from `dagster-postgres`. Introducing Alembic naively would
fight it in the same schema, on a host that auto-deploys every ten minutes.

Schema today is `CREATE TABLE IF NOT EXISTS` called lazily from the writers
that need it - which cannot add a column to a populated table, and cannot run
before the portal starts, which is now required because dbt will depend on the
accounts table.

One ordered, idempotent DDL entry point, called once at portal start rather
than per writer. If Alembic is ever adopted it must be given its own
`version_table`.

## Backfill

Nothing in the first draft covered the live database. On first boot the
operator's existing data must become account #1: adopted and hand-entered
recipes into its saved list, verdicts gaining an account, the store seeded
from `AH_STORE_ID` so the existing `store_id = 1876` history stays theirs,
and the live token bundle moved into the encrypted row **preserving
`refresh_token_issued_at`**, which is the evidence series for AH's expiry
behaviour. Resolutions are touched not at all, and the script should say so.

Rehearse it against a restore of the nightly `vzdump` before running it on
101. That drill is already documented.

## Authorisation

Once operator and user differ, "can a friend press Refresh now?" needs an
answer. On a one-slot queue, four friends pressing it during the scrape window
is a self-inflicted denial of service on the hourly clearance scrape, which
the scheduling spec calls unbackfillable and of absolute priority.

An operator flag, and any action that starts a Dagster run or writes shared
catalogue state is operator-only.

## What this does to existing specs

Six capability specs are contradicted and need deltas:
`deployment-target` and `container-runtime` both state as fact that neither
interface authenticates its callers - and the loopback rule is *derived* from
that, so the rationale must be rewritten or someone later argues the rule
away. `scheduling` says one clearance run per hour is requested, which the
in-asset loop preserves and partitioning would not. `data-quality`'s grain
requirement is activated rather than contradicted, and its single-threshold
freshness cannot express per-account staleness.
