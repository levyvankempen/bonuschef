# portal Specification

## Purpose

Governs how the portal presents pipeline-produced data to a person, so that what is shown carries an honest claim about its currency — particularly for data that perishes within hours of being collected.

## Requirements

### Requirement: Perishable data is not presented as current once stale

Where displayed data describes a fast-changing real-world state — store clearance items, whose discounts deepen through the day and whose stock sells out within hours — the portal SHALL NOT present a snapshot older than the current trading day as though it were current. It SHALL instead state that the data is stale, how old it is, and how to refresh it.

#### Scenario: The snapshot is from today

- **WHEN** the most recent snapshot was taken during the current trading day
- **THEN** the items are shown normally, alongside the time they were captured

#### Scenario: The snapshot is from a previous day

- **WHEN** the most recent snapshot predates the current trading day
- **THEN** the items are not presented as current, and the page states the snapshot's age and offers a refresh

#### Scenario: A stale snapshot is months old

- **WHEN** the most recent snapshot is many weeks old
- **THEN** the page is as clear about staleness as it is for a snapshot one day old, without needing a separate threshold

#### Scenario: No snapshot has ever been taken

- **WHEN** no clearance data exists at all
- **THEN** the page explains that none has been collected yet, distinctly from the case where data exists but is stale

#### Scenario: A refresh succeeds

- **WHEN** an operator refreshes and the scrape succeeds
- **THEN** the page presents the new items as current without a reload being needed

#### Scenario: A refresh fails

- **WHEN** an operator refreshes and the scrape fails
- **THEN** the failure is reported, and the stale data is still not presented as current

### Requirement: Data currency is stated wherever perishable data is shown

The portal SHALL show when a displayed snapshot was captured, in local time, whenever it presents perishable data — whether that data is fresh or stale.

#### Scenario: Fresh data is displayed

- **WHEN** current clearance items are shown
- **THEN** the capture time is visible without interaction

#### Scenario: Local time is used

- **WHEN** a capture time is displayed
- **THEN** it is rendered in Dutch local time, matching the store hours the data describes
