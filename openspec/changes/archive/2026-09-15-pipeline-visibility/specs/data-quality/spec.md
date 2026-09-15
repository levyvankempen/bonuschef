## MODIFIED Requirements

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
