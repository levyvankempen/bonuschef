# Tasks

Section 1 (catalogue content) shipped in #76, before the reviews. It is left
here marked done because task 1.4 has not happened yet.

## 0. Before anything else

- [ ] 0.1 One ordered, idempotent DDL entry point for the new tables, called
      once at portal start rather than lazily per writer. Alembic is Dagster's
      and is not adopted; if it ever is, it needs its own `version_table`
- [ ] 0.2 A test that a fresh database and an existing one converge to the
      same schema
- [ ] 0.3 Backfill script in the established style (argparse, `--dry-run`,
      idempotent): operator account created, existing adopted and hand-entered
      recipes into its saved list, verdicts gaining an account, store seeded
      from `AH_STORE_ID`, token bundle moved into the encrypted row preserving
      `refresh_token_issued_at`. Resolutions untouched, and it says so
- [ ] 0.4 Rehearse the backfill against a restore of the nightly vzdump before
      it runs on 101

## 1. Catalogue content

- [x] 1.1 Adopt R-R1193780, quiche with broccoli and smoked salmon (#76)
- [x] 1.2 Adopt R-R1193969, tacos with kibbeling, red cabbage and aioli (#76)
- [x] 1.3 Withdraw zuurkoolstampot (#76)
- [ ] 1.4 Review what the matcher withheld on the two new recipes

## 2. Accounts

- [x] 2.1 Decided: a cookie component. Not tailnet identity, which would be
      building for the stopgap rather than for a system meant to reach people
      who are not on the tailnet; not a URL token, which puts a live session
      into browser history and into the Referer of every ah.nl link
- [ ] 2.2 Accounts table; sessions in Postgres, revocable, idle lifetime
      enforced against the row on each rerun
- [ ] 2.3 If passwords: scrypt via `cryptography` at `n=2**15, r=8, p=1`,
      parameters stored with the hash. Not `hashlib.scrypt` - OpenSSL's 32 MB
      default cap rejects those parameters
- [ ] 2.4 If passwords: a test asserting the *production* cost constant, with
      the cost monkeypatched down for the rest of the suite. A round-trip test
      does not protect the requirement; the constant assertion does
- [ ] 2.5 If passwords: identical passwords do not produce identical stored
      values; failures are uniform between unknown user and wrong password;
      repeated failures are slowed
- [ ] 2.6 The gate sits in `app.py` above `st.navigation` and ends in
      `st.stop()`, so a page cannot be added unguarded by omission
- [ ] 2.7 The account is passed into page functions as an argument, never a
      module global - the test harness already forwards arguments
- [ ] 2.8 Account-scoped reads live in one module and take the account as a
      first, non-underscored argument. A source-contract test asserts no
      account-scoped query omits the filter, in the style already used
- [ ] 2.9 Every `@st.cache_data` reader of account- or store-scoped data takes
      the account or store as a *hashed* argument. The underscore convention
      excludes a parameter from the cache key, so `_account_id` would serve
      one friend's data to another deterministically
- [ ] 2.10 A test that two accounts in one process do not share a cached frame
- [ ] 2.11 An operator flag. Starting a Dagster run and writing shared
      catalogue state are operator-only
- [ ] 2.12 Sign out; forced password change on first sign-in if passwords

## 3. A store belongs to a person

- [ ] 3.1 Store on the account; `AH_STORE_ID` becomes the default for an
      account that has not chosen, not the source of truth
- [ ] 3.2 Re-source `int_store` from accounts rather than from scraped
      markdowns. Until this is done an account whose store has never been
      scraped gets zero rows from `int_product_offer_today`,
      `int_recipe_item_opportunity` and `fct_recipe_opportunity` - including
      national promotions - so "bonus is still shown" is unachievable
- [ ] 3.3 `clearance_scraped_at` becomes nullable, and its `not_null` test is
      dropped; an unscraped store reads as "no clearance yet", not as a test
      failure
- [ ] 3.4 Filter every store-scoped portal reader. `store_id` currently
      appears once in the whole portal layer and never in a `WHERE`:
      `read_store_clearance`, `read_recipe_opportunity`,
      `read_recipe_opportunity_items`, `read_last_scrape_time`
- [ ] 3.5 `read_last_scrape_time` takes MAX over every store, so a friend
      whose store is stale inherits the operator's freshness and the banner
      lies. Scope it
- [ ] 3.6 A store directory: id to name and city. Asking a friend to type
      "1876" is not a UI, and a typo silently gives another town's prices
- [ ] 3.7 Show the store's name wherever the portal says "jouw winkel"
- [ ] 3.8 Warehouse-marked test: two accounts, two stores, different clearance
      for the same recipe

## 4. Per-user Albert Heijn credentials

- [ ] 4.1 **Settle member-gated vs member-varying by experiment**: two
      credentials, one `storeId`, compare responses. It decides the grain of
      six models and everything below assumes the answer
- [ ] 4.2 A per-account token manager that *cannot* fall back to
      `AH_REFRESH_TOKEN`. `_candidates()` currently includes the bootstrap
      token, so a friend's dead credential would silently refresh with the
      operator's and return their clearance under the friend's store name
- [ ] 4.3 A `TokenStore` protocol and a Postgres-backed implementation keyed
      on the account, preserving the manager's rotation semantics. The shared
      `AH_TOKEN_FILE` must never be reached for a non-operator account
- [ ] 4.4 Encrypted credential column: AESGCM, key from `.env`, `account_id`
      as associated data so a ciphertext cannot be moved between rows,
      `key_id` for rotation
- [ ] 4.5 The key reaches both the Dagster and the Streamlit containers - the
      portal connects credentials, Dagster refreshes them
- [ ] 4.6 Connect flow: a guided page that accepts the authorization code
      copied out of the blocked `appie://login-exit` redirect, or the whole
      URL, and exchanges it immediately. There is no server-side callback to
      build. Document the operator-assisted fallback
- [ ] 4.7 Record and display when a credential was last used. Nothing writes
      this today and the requirement demands it
- [ ] 4.8 Disconnect: credential deleted, clearance stops, recipes untouched
- [ ] 4.9 Redact: a `__repr__` that cannot leak the token, an audit of
      `AHAuthError`'s `resp.text[:200]`, and no reuse of `ah_login.py`'s
      deliberate stdout print for a friend's flow
- [ ] 4.10 Test with no DB and no network: wrong key fails, wrong account as
      associated data fails, no credential appears in any log record
- [ ] 4.11 The token heartbeat exercises every credential, reports each
      separately, and one failure neither fails the others nor pages hourly
- [ ] 4.12 Walk one friend through connecting, end to end, before inviting the
      rest

## 5. Clearance per store

- [ ] 5.1 Loop over stores inside the existing asset. Not partitions:
      `max_concurrent_runs: 1` is deliberate, the downstream rebuild is
      all-stores, and 35 of the job's 39 seconds is process startup
- [ ] 5.2 Per-store failure is asset metadata; the asset fails only when every
      credential is rejected
- [ ] 5.3 Per-store clearance staleness, surfaced on that account's page and
      in pipeline health. A single freshness threshold over the whole table
      stays green forever if the operator's store keeps scraping
- [ ] 5.4 Bonus ingestion stays national and a single fetch
- [ ] 5.5 An account without a credential sees bonus prices and a stated
      reason for absent clearance - which depends on 3.2

## 6. Recipes

- [ ] 6.1 Saved-recipe join per account; last-made date; notes
- [ ] 6.2 Verdicts gain an account. Today one person's "niet voor mij" hides a
      recipe from everyone
- [ ] 6.3 The pool exclusion becomes account-scoped. Today one person adopting
      removes the recipe from everyone else's pool, which contradicts this
      change's own "a recipe another account adopted can still be saved"
- [ ] 6.4 Overrides on **saved recipes only**, as an overlay keyed on
      (account, recipe, item), never as an account dimension on the pool
- [ ] 6.5 A third `source_kind` for an edited line that resolves to nothing.
      Without it the shape test and "the edit is kept and shown as unresolved"
      cannot both hold
- [ ] 6.6 `fct_recipe_cost_latest` and `fct_recipe_cost_breakdown` gain
      `account_id`; `fct_recipe_cost_history` deliberately does not, and the
      spec says why
- [ ] 6.7 Test that one account's edit is invisible to another

## 7. The recipes page

- [ ] 7.1 Cards with image, title, cost, coverage and last-made. Reuse the
      existing brief card rather than inventing a second card idiom
- [ ] 7.2 Delete the detail pane and the duplicate highlights block - the page
      renders the same rows three times and makes you re-select a recipe you
      are already looking at
- [ ] 7.3 Confirm the card path still satisfies "a wrong match is correctable
      where it is visible", which the deleted detail pane satisfied
- [ ] 7.4 Filter to what is on offer today, with the count in the label before
      it is applied, and what each card matched on
- [ ] 7.5 Lift the stale-clearance withdrawal out of the tonight page into one
      shared helper. Two pages each deciding what "current" means is how two
      surfaces come to disagree about one snapshot
- [ ] 7.6 Three distinct degraded states, not one: no store chosen, no
      credential connected, snapshot stale
- [ ] 7.7 Empty and partial states that read as answers
- [ ] 7.8 Mark as made, from the card, with a correction path
- [ ] 7.9 Default sort is longest-not-made
- [ ] 7.10 Bound the reader and render ingredient lists lazily; the existing
      spec forbids unbounded reads for a bounded view
- [ ] 7.11 Edit in a dialog, opened from session state rather than from inside
      a button branch - a full rerun re-evaluates the branch as false and the
      dialog vanishes with the draft. Dialogs cannot nest, so a correction
      hands off rather than drilling down
- [ ] 7.12 Report the edit outcome on the page, not in the dialog; a rerun
      closes the dialog and the message is never seen
- [ ] 7.13 Show the already-saved state on the tonight page before the click.
      `is_kept` exists and is called nowhere
- [ ] 7.14 AppTest coverage of the dialog, not assertions on source text
- [ ] 7.15 New copy passes the language test

## 8. Cross-capability specs

- [ ] 8.1 `deployment-target` and `container-runtime` both state that neither
      interface authenticates its callers, and the loopback rule is derived
      from that. Rewrite the rationale, keep the rule
- [ ] 8.2 `scheduling`: one clearance run per hour still holds under the
      in-asset loop; say so rather than leaving it contradicted
- [ ] 8.3 `data-quality`: the grain requirement is activated; per-account
      staleness needs more than one threshold
- [ ] 8.4 `recipe-catalogue`: resolutions stay shared, ingredient lines become
      per-account. Three existing requirements say a correction applies to
      every recipe using that ingredient and must survive
- [ ] 8.5 `openspec/config.yaml` still says "personal" and "one maintainer"

## 9. Before friends are invited

- [ ] 9.1 Confirm the portal is reachable only over the tailnet
- [ ] 9.2 Tell the people being invited what is stored about their AH account
      and how to end it
- [ ] 9.3 Confirm a restart does not sign everyone out
- [ ] 9.4 Re-run the restore drill against the new credential scheme - a
      vzdump no longer restores a working system if the key lives outside it
