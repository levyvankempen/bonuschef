# data-quality Specification

## Purpose

Defines the guarantees the warehouse makes about its own output — that each table holds the grain it claims, that references resolve, that inputs are fresh enough to describe the present, and that a record is never dropped quietly — so a defect surfaces as a failure rather than as a plausible wrong number.

## Requirements

### Requirement: Every published table holds a declared grain

Each published table SHALL declare the combination of columns that uniquely identifies a row, and that combination SHALL be tested. A table SHALL NOT declare a grain narrower than the one it actually holds.

#### Scenario: A build introduces duplicate rows

- **WHEN** a change causes a table to emit more than one row per declared key
- **THEN** the build fails rather than publishing the duplicates

#### Scenario: A grain that anticipates more than one store

- **WHEN** a table's rows are scoped to a store
- **THEN** its declared key includes the store, so adding a second store does not silently break its meaning

### Requirement: Stale sources are reported

Every source SHALL declare how recently it must have loaded to be considered current, and a source that falls behind SHALL be reported.

Those declarations SHALL be evaluated on a schedule. A threshold that nothing ever runs is a comment, and this project has already served a feed's July rows as current for 69 days with the thresholds declared the whole time.

#### Scenario: A feed stops loading

- **WHEN** a source has not loaded within its declared tolerance
- **THEN** that is reported as a failure of freshness, without waiting for someone to notice the data looks wrong

#### Scenario: Different sources have different tolerances

- **WHEN** freshness is evaluated
- **THEN** each source is judged against its own cadence, so an hourly scrape and a weekly snapshot are not held to one threshold

#### Scenario: A threshold that is never evaluated

- **WHEN** a freshness threshold is declared
- **THEN** something runs it on a schedule, rather than the declaration existing only in configuration

### Requirement: Records are not dropped silently

Where a record cannot be enriched — an unresolvable reference, a missing price — the warehouse SHALL retain the record with the affected measures marked unknown. It SHALL NOT omit the record, and SHALL NOT substitute a default value that would read as a real measurement.

#### Scenario: A recipe whose ingredients cannot be priced

- **WHEN** none of a recipe's ingredients resolve to a known price
- **THEN** the recipe is still published, with its cost reported as unknown rather than absent from the table

#### Scenario: A partially priced basket

- **WHEN** only some of a basket's items have known prices
- **THEN** the total is either reported as unknown or clearly marked partial, and never presented as a complete total

#### Scenario: A missing price is not zero

- **WHEN** a price is unknown
- **THEN** it is represented as unknown, so it cannot be summed as though the item were free

### Requirement: References between records are tested

Where one record refers to another, that reference SHALL be tested. A reference that does not resolve SHALL be reported rather than silently removing the referring record from downstream results.

#### Scenario: A recipe ingredient points at an unknown product

- **WHEN** an ingredient references a product identifier that is not in the catalogue
- **THEN** this is reported, rather than the ingredient quietly disappearing from the recipe's cost

#### Scenario: A reference failure does not stop the build

- **WHEN** a reference fails to resolve because a user typed it by hand
- **THEN** the condition is reported as a warning, so one bad entry does not block every other result

### Requirement: Values are constrained to what the domain permits

Measures SHALL be tested against the bounds their domain allows, so that an impossible value is caught at build time.

#### Scenario: A discounted price above its own reference

- **WHEN** a marked-down price exceeds the price it was marked down from
- **THEN** the condition is reported

#### Scenario: A percentage outside its range

- **WHEN** a discount percentage falls outside nought to one hundred
- **THEN** the condition is reported

#### Scenario: An unexpected category value

- **WHEN** a categorical field carries a value outside its known set
- **THEN** the condition is reported, because consumers translate those values for display and would otherwise show a raw code
