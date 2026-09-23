# Tasks

Section 1 (catalogue content) shipped in #76, before the reviews. It is left
here marked done because task 1.4 has not happened yet.

## 0. Before anything else

- [x] 0.1 One ordered, idempotent DDL entry point (#77). Alembic is Dagster's
      and is not adopted
- [x] 0.2 Idempotency tests, two of them mutation-verified (#77)
- [x] 0.3 Backfill script (#77, #78). No credential to move now that there is
      only one; resolutions untouched, and it says so
- [x] 0.4 Rehearsed against a clone of the live database rather than a vzdump
      restore - it tests the migration against the real rows without needing a
      container restore. Found that --dry-run was applying the DDL (#78)

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
- [x] 2.2 Accounts table (#77); sessions in Postgres, revocable, idle
      lifetime enforced against the row on each lookup (#86)
- [x] 2.3 scrypt via `cryptography` at `n=2**15, r=8, p=1` (#85). Not
      `hashlib.scrypt`, whose OpenSSL cap rejects those parameters - pinned
      by a test asserting hashlib DOES raise
- [x] 2.4 The production cost asserted from the dataclass defaults, with the
      suite monkeypatched down to n=2**10 (#85)
- [x] 2.5 Salting, and a uniform refusal that also costs the same work for an
      unknown username as for a wrong password (#85, #86). Rate limiting is
      still open - see 2.13
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
- [x] 2.12 Sign out (#86); new accounts are created must-change (#87)
- [ ] 2.13 Slow repeated failures. The uniform message and matched timing are
      in place; nothing yet limits how fast they can be tried
- [x] 2.14 An operator path to create accounts and set passwords (#87). Had to
      exist BEFORE the gate: password_hash defaults to empty, an empty hash
      verifies against nothing, and a gate over an account that cannot sign in
      locks out the person who would fix it

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
- [x] 3.4 Filter every store-scoped portal reader (#79)
- [x] 3.5 Scope `read_last_scrape_time`, which took MAX over every store (#79)
- [x] 3.6 A store directory from `storesSearch`: 1,199 stores with names (#80)
- [ ] 3.7 Show the store's name wherever the portal says "jouw winkel"
      (the directory it needs shipped in #80)
- [ ] 3.8 Warehouse-marked test: two accounts, two stores, different clearance
      for the same recipe

## 4. Albert Heijn credentials

Measured 2026-09-20: `bargainItems` is store-scoped and auth-gated, not
member-varying - one credential reads any store's clearance. Per-user
credentials are therefore not needed for correctness, and this section is
almost entirely deleted. See design.md for the measurement.

- [x] 4.1 Settle member-gated vs member-varying by experiment. **Gated.**
- [ ] 4.2 The single credential fetches each distinct store. Keep it the
      operator's, in the existing token file; no per-account credential, no
      encryption scheme, no connect flow, no revocation UI
- [ ] 4.3 Guard the assumption: if a store ever returns another store's
      contents, or a credential is rejected for a store that is not its own,
      that is the measurement going stale and must be visible rather than
      silently wrong

Deleted with this section, and worth naming because they were the most
expensive and most dangerous parts of the change: holding friends' Albert
Heijn sessions, encrypting them at rest, rotating the key, revoking a
connection, fanning the heartbeat out per account, and asking a friend to
copy an authorization code out of desktop DevTools.

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
- [ ] 5.5 A store with no clearance shows that as an answer, not a failure.
      Store 5557 returned zero items in the measurement while its neighbours
      returned hundreds; an empty list is a real state

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
- [ ] 9.4 The restore drill is unchanged: the credential stays the single
      token file that the last drill already verified survives a restore
