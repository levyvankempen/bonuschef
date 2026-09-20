# A green check should be evidence

## Why

CI has been green for every one of these:

- An auto-deploy script that deleted its own executable on the first
  rollback. Sixteen tests passed, and every one of them copied the script
  *into* a checkout and ran it from there — reproducing exactly the layout the
  change had just removed.
- A release gate that could not run the tests it named, so no version was cut
  for two months. CI passed throughout, because CI happened to run the
  sessions in a different order.
- A test called `test_the_verification_runs_the_same_checks_as_ci` that never
  opened `ci.yml`. It did not fail to catch the drift; it pinned the drift in
  place and named itself after the guarantee it was breaking.
- A test asserting that a brand preference must not decide which *kind* of
  product to propose, which passed while checking nothing — another signal
  dominated the constructed case, so the flag under test never mattered.
  Found only by hand-mutating the source.
- SQL that `sqlfluff fix` had corrupted: `> {{ var('x') }}` rewritten as
  `> i.{{ var('x') }}`, which renders to `i.45`. 446 tests passed, the linter
  passed, `dbt parse` passed. Only a database rejects `i.45`.
- A portal query that joined two tables and selected nothing from either,
  four separate times. pandas returns `None` for an absent column, so the
  page said "van geen enkel ingrediënt is de prijs bekend" over six priced
  products instead of raising.
- A correction pass that was right in principle and repaired no actual rows,
  because the rules it applied could not object to any of the wrong data.

Auto-merge was just enabled. It is only ever as good as the checks it waits
on, and on this evidence the checks are not yet worth waiting for.

## What Changes

The check list starts producing evidence rather than a timestamp.

- A database in CI, so rendered SQL is executed rather than parsed. This is
  the cheapest item and it catches two of the seven on its own.
- What a page reads is checked against what its query returns, replacing the
  fifth iteration of a regex that has stopped biting four times.
- Checks that claim two files agree read both files.
- Checks run the arrangement production uses, not the one that is convenient
  to construct.
- A guard is not trusted until it has been seen failing.

## Impact

- Affected specs: `verification` (new), `release`
- Affected code: `.github/workflows/ci.yml`, `noxfile.py`, `tests/unit/`,
  a seeded fixture, `docker-compose` for the CI database

## Out of scope, and deliberately

These are the versions of this that get abandoned in a month.

- **A mutation-testing framework.** The textbook answer to the test that
  asserted nothing, and the wrong one here: the suite cannot be collected
  without `dbt deps && dbt parse`, so every mutant pays that startup. The
  discipline is kept; the tool is not.
- **A coverage threshold.** All seven failures happened on covered lines,
  several on lines covered by the test that was lying. A percentage gate
  would have been green throughout while taxing every change.
- **A staging environment.** It doubles what one person maintains, and would
  itself drift into being a configuration production does not use — which is
  the first failure on the list.
- **Live AH calls in CI.** A real credential, hCaptcha, and rate limits on
  the critical path of every change.
