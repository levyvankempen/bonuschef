# Design

## The database is the cheapest thing here

Five of the seven failures are invisible without one, and two of them are
caught by a database with *no data in it at all* — the corrupted Jinja and the
reader that selects nothing both fail on an empty warehouse, because the SQL
is executed either way.

So the first increment is a Postgres service in the CI job and `dbt build`
against it. The warehouse is about twenty models and six singular tests, and
`profiles.yml` records a 10.6s full build at two threads. This is under a
minute of CI for the two most expensive classes of bug in the list.

`dbt parse` stays in the nox session, because the test suite needs the
manifest to import the Dagster definitions and must remain runnable without a
database. `dbt build` becomes a separate session that requires one. The two
are not alternatives: parse is what makes the suite collectable, build is what
makes the SQL true.

## Not path-gated

It is tempting to build the warehouse only when a warehouse file changes.
That rebuilds the second failure on the list: a conditionally-run check is one
that is not run. A Python change that renames a column a page reads needs the
warehouse to catch it, and the whole thing is under a minute.

The container image build *is* path-gated, because that one is genuinely slow.

## Replacing the column heuristic rather than refining it

`test_portal_query_columns.py` is a regex over SELECT clauses whose own
docstring records four earlier forms that each stopped biting — a substring
match that accepted `url` inside `image_url`, a version satisfied by a
comment, one where a JOIN condition vouched for a column the SELECT never
returned.

With a built warehouse the question has an exact answer: execute the reader,
look at the columns it returns, compare against what the page reads. The
heuristic is deleted in the same change. Keeping both would leave the cheap
wrong one standing in for the expensive right one, which is how it survived
four rewrites.

## Observing a guard fail

This is a habit, not a tool. A mutation-testing framework is the textbook
answer and the wrong one: the suite cannot be collected without `dbt deps &&
dbt parse`, so every mutant pays that startup, and the survivors would be
overwhelmingly logging and formatting.

What goes in is a convention: a change that adds a guard records, in its
tasks, the one-line edit to the source that made the guard fail. Two minutes
at authoring time, and it is the only thing that would have caught the test
that asserted nothing.

## What the fixture is for, and how it stays small

Requirements 5-7 want data. The temptation is a synthetic corpus built
up-front, which is the version that gets abandoned.

Instead it grows one row at a time, and only from incidents: when a defect in
derived data is fixed, the row that exhibited it is captured. Today that is
"mierikswortel in pot" resolving to peanut butter, and "cannellinibonen in
blik" resolving to tuna. Tens of rows, each of which has already proved it was
worth having.

## What this does not attempt

A staging tier, a browser driver, live retailer calls in CI, and a coverage
gate are all excluded. The coverage gate is worth naming explicitly: all seven
failures happened on covered lines, several on lines covered by the very test
that was lying. It would have been green throughout while taxing every change.
