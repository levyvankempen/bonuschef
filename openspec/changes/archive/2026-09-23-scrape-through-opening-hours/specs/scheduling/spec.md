# scheduling

## ADDED Requirements

### Requirement: The clearance scrape runs hourly through opening hours

The pipeline that scrapes store clearance ("laatste kans koopjes") markdowns SHALL be scheduled once per hour from 08:00 through 21:00 Dutch local time. The intraday sequence of runs is what records how a markdown deepens over a day, so the cadence SHALL NOT be reduced to a single daily run.

The window tracks the hours the shop is open rather than the hours markdowns were assumed to appear. The previous window began at 11:00 on the belief that the store publishes no markdowns before midday - an assumption, never an observation. A scrape that finds nothing is a recorded answer; an hour with no scrape is a gap the portal cannot tell apart from a failure, and it reported one every morning.

#### Scenario: Opening hours

- **WHEN** the clock reaches the top of any hour from 08:00 through 21:00 Dutch local time
- **THEN** one clearance scrape run is requested for that hour

#### Scenario: The last hour before closing

- **WHEN** the clock reaches 21:00 Dutch local time
- **THEN** a scrape is still requested, because a markdown is deepest and least likely to survive the night in the hour before closing

#### Scenario: Closed hours

- **WHEN** the clock reaches the top of an hour outside 08:00 through 21:00 Dutch local time
- **THEN** no clearance scrape run is requested, because the shop is shut and its shelves are not being marked down

#### Scenario: A scrape that finds nothing

- **WHEN** a scrape runs during opening hours and the store has no markdowns
- **THEN** the run is still recorded as having happened, so an empty result is distinguishable from an hour that was never scraped

## REMOVED Requirements

### Requirement: The clearance scrape runs hourly through the afternoon
