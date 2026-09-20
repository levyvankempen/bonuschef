## Purpose

A green check is a claim that a change is correct. This capability makes the
claim true, so that "CI passed" is evidence rather than a timestamp. Every
requirement here is traceable to a change that passed its checks and shipped
broken.

## ADDED Requirements

### Requirement: Rendered SQL is executed, not merely parsed

Every model, macro and test in the warehouse project SHALL be compiled and
executed against a real database as part of the check list. Parsing SHALL NOT
stand in for execution.

A formatter once rewrote `> {{ var('max_price_age_days') }}` into
`> i.{{ var('max_price_age_days') }}`, which renders to `i.45`. 446 tests
passed, the SQL linter passed, and parsing passed — because Jinja renders to
text that looks valid. Only a database rejects `i.45`, and it was caught by a
build run by hand against production.

#### Scenario: A formatter corrupts a templated expression

- **WHEN** a rewrite produces SQL that lints clean and renders to nonsense
- **THEN** the check list fails, naming the model or test that would not run

#### Scenario: A column is removed from a model

- **WHEN** a model stops producing a column that something downstream selects
- **THEN** every dependent model and test fails in the same run, rather than at page load on the deployed host

#### Scenario: The warehouse is checked on every change

- **WHEN** a change touches no warehouse file
- **THEN** the warehouse is still built, because a change elsewhere can break what reads from it

### Requirement: What a page reads is checked against what its query returns

A column that a page reads SHALL be verified against the result the query
actually produces when executed, not against the text of the query.

This has shipped four times. A reader joined two tables and selected nothing
from either; the dataframe had no such column; pandas returns nothing for an
absent column rather than raising, so the page reported that no ingredient had
a known price while showing six priced products.

#### Scenario: A reader selects nothing from a table it joins

- **WHEN** a query is executed and a page reads a column the result does not contain
- **THEN** the check fails, naming both the column and the page

#### Scenario: A mart renames a column a page depends on

- **WHEN** a published table stops offering a column a page reads
- **THEN** the check fails in the same run as the rename

#### Scenario: A new page is added

- **WHEN** a page is added that reads from the warehouse
- **THEN** it is covered without anyone adding it to a list, or the checks fail until it is

### Requirement: A check that claims two files agree reads both

A check asserting that two artefacts are consistent SHALL derive both sides
from their sources when it runs. A transcribed copy of one side is not such a
check.

A test named for the guarantee that the release gate matches CI hardcoded
three session names and never opened the CI workflow. It did not merely fail
to catch the drift — it held the drift in place, under a name that said
otherwise.

#### Scenario: A workflow starts running something the canonical list omits

- **WHEN** a gate invokes project checks that are not the canonical list
- **THEN** the check fails, naming the workflow and what it runs

#### Scenario: The canonical list grows

- **WHEN** a check is added to what runs on a proposed change
- **THEN** every gate picks it up without a second list being edited

#### Scenario: Such a check fails

- **WHEN** two artefacts are found to disagree
- **THEN** the message quotes both sides as read from their sources, so the failure can be understood without opening the check

### Requirement: A check exercises the arrangement production uses

A check SHALL exercise code in the arrangement production runs it in — the
installed location, the invocation, and the way it finds its inputs. A check
SHALL NOT be the only coverage of a behaviour while placing the code somewhere
production does not.

Sixteen tests covered a deploy script. Every one copied it into a checkout and
ran it from there, which was precisely the layout the change under test had
removed. The tests described the old world, confidently, and the script failed
on the first real invocation.

#### Scenario: Code is installed outside the tree it operates on

- **WHEN** a script is installed somewhere other than the checkout it acts on
- **THEN** at least one check runs it from the installed location, finding its inputs only the way production does

#### Scenario: A change moves where code lives or how it is found

- **WHEN** a change alters an installed path or a lookup mechanism
- **THEN** the checks covering it move with it; checks that stay green across such a move are a defect in the checks

#### Scenario: A fixture substitutes for a production component

- **WHEN** a stand-in replaces a component a check does not mean to exercise
- **THEN** it replaces that component's effects only, never the path or lookup under test

### Requirement: A guard has been observed failing

A check SHALL be demonstrated capable of failing against the defect it exists
to catch, and the change that introduces it SHALL record that demonstration.

A test asserting that a brand preference must not decide which kind of product
to propose passed while checking nothing: another term in the scoring dominated
the constructed case, so the flag under test could not have changed the answer
either way. It was found by mutating the source by hand.

#### Scenario: A check asserts an input has no effect

- **WHEN** a check asserts that some input must not influence an outcome
- **THEN** the same case also shows the outcome changing when that input is allowed to act, so a case where nothing could have changed cannot pass

#### Scenario: A new guard is added

- **WHEN** a check is added for an invariant
- **THEN** the change records the change to the source that made it fail, because a check never seen red is not yet evidence

### Requirement: A fix shows the outcome changing on data that reproduces it

A change whose purpose is to correct wrong output SHALL demonstrate that
outcome changing on at least one record that exhibits it. A correction that
changes no record SHALL fail.

A pass intended to repair bad ingredient matches was correct in principle and
repaired nothing: the rules it applied could not object to tuna, pesto or
peanut butter, which is what the bad rows actually contained. The unit tests
proved the mechanism ran. Only the data showed it achieved nothing.

#### Scenario: Derived data is corrected

- **WHEN** a defect in derived output is fixed
- **THEN** a record exhibiting it is held as fixture data, and a check asserts the outcome is wrong before the change and right after

#### Scenario: A correction pass runs

- **WHEN** a fix takes the form of a pass over existing records
- **THEN** a check asserts it repairs more than zero of them, and separately that the records it must not touch are unchanged
