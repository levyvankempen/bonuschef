# Tasks

## 1. Checks that read both sides

- [x] 1.1 The CI/gate comparison reads both workflows and the noxfile at run
      time; it already did, but only in one direction
- [x] 1.2 Made bidirectional. The unguarded direction had already diverged:
      the release gate ran `format_python` and `format_sql`, which REWRITE
      the tree, so it was modifying the code before checking it and verifying
      something other than the commit it was about to release. Both removed
      from the check list; their checking equivalents already run
- [x] 1.3 Negative control: putting either back into `nox.options.sessions`
      fails `test_no_gate_runs_a_session_that_rewrites_the_tree`

## 2. Checks that run the production arrangement

- [ ] 2.1 Audit the script tests for fixtures that reproduce a layout
      production does not use
- [ ] 2.2 Cover the installed arrangement where one exists
- [ ] 2.3 Negative control for each

## 3. A database in CI

- [x] 3.1 Postgres service in `ci.yml` **and `release.yml`** - a gate that
      cannot run the list is the v1.3.0 failure from the other direction
- [x] 3.2 `nox -s warehouse` runs `dbt build`; `_dbt_parse` stays, because the
      suite needs the manifest and must stay runnable without a database
- [x] 3.3 Not path-gated
- [x] 3.4 **Negative control, run:** reintroduced `> i.{{ var(...) }}`.
      `sqlfluff lint` said "All Finished!"; the warehouse session said
      `Database Error ... syntax error at or near ".45"`. 171 PASS / 0 ERROR
      clean, 35 seconds
- [x] 3.5 Source tables the warehouse reads but does not create: the portal's
      own `ensure_catalogue_tables` is CALLED rather than copied; only the
      five dlt-created tables are restated, and a missing column fails the
      build by name

## 3b. Silent skips

- [x] 3b.1 Six tests covering the SQL behind `portal/db.py` skipped themselves
      in CI from the day they were written. With a database present, a skip in
      CI is now a failure; locally it still skips. 46 passed, 0 skipped

## 4. Readers checked against what they return

- [ ] 4.1 Execute each portal reader against the built warehouse and compare
      its columns with what the pages read
- [ ] 4.2 Delete `test_portal_query_columns.py`
- [ ] 4.3 Confirm the new check catches what the old one was written for

## 5. Write the habit down

- [ ] 5.1 Record the negative-control convention where a change author will
      see it


## 6. Found while doing this

- [x] 6.1 The asset wrote to `ah_ingredient_flags` without creating it, and
      failed in production on `relation ... does not exist`. Every unit test
      of that path monkeypatched `flag_concepts`, so the write that needed
      the table never happened - the tests stubbed out precisely the thing
      that broke. This is requirement 4's own subject matter, found while
      writing requirement 4
- [x] 6.2 The fix is checked by comparing what `db.py` writes to against what
      it creates, so a second table added the same way cannot fail the same
      way
