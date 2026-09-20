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

- [x] 2.1 Audited. Findings:
      * `test_deploy_script.py` and `test_version.py` copy their script into a
        checkout and run it there, which IS where production keeps them - no
        mismatch
      * `test_auto_deploy.py` covers both the in-checkout and the installed
        `/usr/local/bin` arrangement, since #51
      * the real one: `auto-deploy.sh` calls `deploy.sh` and branches on its
        exit code, and the fixture replaces `deploy.sh` with a recorder told
        which code to exit with. The number the two scripts must agree on was
        INVENTED BY THE FIXTURE. Both suites pass with them disagreeing -
        verified, 27 passed
- [x] 2.2 The fixture now reads the code from `deploy.sh` instead of stating
      it, and a contract test compares what `deploy.sh` exits with against
      what `auto-deploy.sh` retries on
- [x] 2.3 **Negative control, run.** Changing deploy.sh's in-flight exit from
      75 to 76: before, 27 passed; after, the contract test fails naming both
      numbers and the auto-deploy in-flight test fails with it

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

- [x] 4.1 Each reader is executed against the built warehouse and its returned
      columns compared with what the pages read. An empty warehouse suffices -
      pandas returns the column names of a result set with no rows
- [x] 4.2 `test_portal_query_columns.py` deleted, not refined a fifth time
- [x] 4.3 **Negative control, run twice.** Dropping `opportunity_rank` from a
      SELECT: both catch it. The bug the new check FOUND on its first run -
      `read_pipeline_health`'s fail-soft path returning 4 columns where the
      happy path returns 7 - old heuristic 5 passed, new check failed naming
      `is_overdue` and `what`. The old one had been green on that for its
      entire life, because it reads SQL text and this is runtime shape

## 5. Write the habit down

- [x] 5.1 Recorded in `openspec/config.yaml`, which is shown to whoever
      creates a change, along with the reason


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
