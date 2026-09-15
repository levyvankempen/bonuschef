# release Specification

## Purpose

A released version is a claim that the code behind it passed the project's
checks. This capability is what makes that claim true, so that a version
number is evidence rather than decoration.

## Requirements

### Requirement: A release is gated by the same checks as a change

The checks that run before a release SHALL be the same checks that run on a
proposed change. They SHALL NOT be two separately maintained lists.

Two lists drift, and the drift is silent until it matters. The v1.3.0
release failed on exactly this: the release gate named a subset of sessions
that omitted the one producing the dbt manifest, so the suite could not even
be collected. The weaker gate was the one guarding the tag.

#### Scenario: A session is added to the project's checks

- **WHEN** a new check is added to what runs on a proposed change
- **THEN** it also runs before a release, without anyone editing a second list

#### Scenario: The checks fail on the release branch

- **WHEN** the checks do not pass
- **THEN** no version is tagged and no release is published

### Requirement: A check produces what it needs

Running any single check on a clean checkout SHALL succeed. A check SHALL
NOT depend on a build artefact that a different check happens to leave
behind.

#### Scenario: The test suite is run on its own

- **WHEN** the test suite is run on a checkout where nothing else has run
- **THEN** it passes, rather than failing to collect because a generated file is absent

#### Scenario: A generated artefact is already present

- **WHEN** the artefact a check needs has already been produced
- **THEN** producing it again is harmless, so check order remains free
