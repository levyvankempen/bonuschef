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
- [x] 1.4 Reviewed on the live database: nothing withheld. All 5 quiche
      ingredients and all 10 taco ingredients resolve, including the one that
      had gone wrong - wit scharrelei was linked to DeLoach Chardonnay, the
      recheck withdrew it once daily_refresh could run again, and it now
      resolves to seven kinds of egg
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
- [x] 2.6 The gate sits above st.navigation and ends in st.stop() (#90)
- [x] 2.7 Pages take the account as an argument; SINGLE_USER stands in with the wall down (#97)
- [x] 2.8 Account-scoped reads live in db.py and take the account as a first, hashable argument (#97, #98)
- [x] 2.9 Verified by an AST sweep: no cached reader touches an account or store without taking it (#99)
- [x] 2.10 Two accounts in one process get different answers, against real Postgres (#99)
- [x] 2.11 Only an operator may start a run (#98)
- [x] 2.12 Sign out (#86); new accounts are created must-change (#87)
- [x] 2.13 Five failures in fifteen minutes, counted in Postgres (#94)
- [x] 2.14 An operator path to create accounts and set passwords (#87). Had to
      exist BEFORE the gate: password_hash defaults to empty, an empty hash
      verifies against nothing, and a gate over an account that cannot sign in
      locks out the person who would fix it

## 3. A store belongs to a person

- [x] 3.1 Store on the account; AH_STORE_ID is the fallback for the wall-down case (#98)
- [x] 3.2 int_store is built from the stores accounts use (#95)
- [x] 3.3 clearance_scraped_at is nullable; the not_null tests are gone (#95)
- [x] 3.4 Filter every store-scoped portal reader (#79)
- [x] 3.5 Scope `read_last_scrape_time`, which took MAX over every store (#79)
- [x] 3.6 A store directory from `storesSearch`: 1,199 stores with names (#80)
- [x] 3.7 The clearance page names the shop (#98)
- [x] 3.8 Two accounts, two stores, different clearance (#99)
## 4. Albert Heijn credentials

Measured 2026-09-20: `bargainItems` is store-scoped and auth-gated, not
member-varying - one credential reads any store's clearance. Per-user
credentials are therefore not needed for correctness, and this section is
almost entirely deleted. See design.md for the measurement.

- [x] 4.1 Settle member-gated vs member-varying by experiment. **Gated.**
- [x] 4.2 One credential fetches every store (#95)
- [x] 4.3 Two shops returning identical shelves is reported. The measurement
      that one credential serves every shop was made once; if it stops
      holding, every friend silently reads somebody else's prices
## 5. Clearance per store

- [x] 5.1 A loop inside the asset, not partitions (#95)
- [x] 5.2 Per-store failure is a warning; only every store failing is a failure (#95)
- [x] 5.3 A shop falling behind the others is said on its own page. One run
      scrapes every shop and a failing shop is a warning, so a green run
      stopped meaning this shop was scraped
- [x] 5.4 Bonus stays national and a single fetch - unchanged, and now covered by a test that an unscraped store still sees it (#95)
- [x] 5.5 A never-scraped shop reads as "nog nooit gescand" rather than as a
      failure, and an empty scrape as "geen koopjes"
## 6. Recipes

- [x] 6.1 Saved-recipe join per account (#97). last_made_at and notes exist as columns; nothing writes them yet - see 7.8
- [x] 6.2 Verdicts are keyed on (account, recipe) (#97)
- [x] 6.3 The pool exclusion moved to the portal, which knows who is asking (#97)
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

- [x] 7.1 Cards with image, title, cost, coverage, what made it cheap, and
      last-made. The brief card from Vanavond rather than a second idiom
- [x] 7.2 The detail pane and the duplicate bonus block are gone - the page
      rendered the same rows three times
- [x] 7.3 The card carries the ingredient lines and the correction, so
      deleting the detail pane did not quietly regress a live requirement
- [x] 7.4 The on-offer filter, with the count in the label before it is
      applied
- [x] 7.5 The stale-clearance withdrawal lives in offers.py; both pages use it
- [x] 7.6 Never scraped, stale, and current are three different sentences.
      No-credential is not a state any more - there is one credential
- [x] 7.7 Nothing saved links to where recipes come from; nothing on offer
      answers the next question instead of showing an empty grid
- [x] 7.8 Mark as made, from the card
- [x] 7.9 Default sort is longest-not-made
- [x] 7.10 The lines are fetched only for the card that is open, because an
      expander renders its contents whether or not it is expanded
- [ ] 7.11 Edit in a dialog, opened from session state rather than from inside
      a button branch - a full rerun re-evaluates the branch as false and the
      dialog vanishes with the draft. Dialogs cannot nest, so a correction
      hands off rather than drilling down
- [ ] 7.12 Report the edit outcome on the page, not in the dialog; a rerun
      closes the dialog and the message is never seen
- [x] 7.13 The tonight page says a recipe is already saved before the click.
      is_kept had existed since keeping did and was called by nothing
- [ ] 7.14 AppTest coverage of the dialog, not assertions on source text
- [x] 7.15 New copy passes the language test
## 8. Cross-capability specs

- [x] 8.1 deployment-target and container-runtime say what is true now (#100)
- [x] 8.2 scheduling says one run per hour still holds with several shops (#100)
- [x] 8.3 data-quality says why the grain requirement mattered before there
      was a second shop, and that per-shop staleness needs more than one
      threshold over the whole table
- [x] 8.4 recipe-catalogue says a resolution applies to every account, because
      which product satisfies an ingredient is a fact rather than a
      preference (the ADDED requirement for this landed earlier)
- [x] 8.5 config.yaml no longer calls the project personal (#100)
## 9. Before friends are invited

- [x] 9.1 Verified on the server: 8501, 3000 and 5455 all bind to 127.0.0.1 only
- [x] 9.2 docs/for-people-invited.md. Shorter than this task expected:
      nothing about their Albert Heijn account is stored, because per-user
      credentials were measured to be unnecessary and deleted
- [x] 9.3 Verified by restarting the portal: three live sessions survived
- [x] 9.4 Verified unchanged: no per-account credential, no key outside the database, and ah_tokens.json still mode 600 on the volume
