## ADDED Requirements

### Requirement: Credential upkeep runs on its own schedule

A scheduled pipeline SHALL exist whose only purpose is to keep member credentials fresh, running at least daily. Its schedule SHALL be independent of the data pipelines, so that disabling, retiming or failing a data pipeline does not stop credential upkeep.

#### Scenario: The data pipelines are paused

- **WHEN** an operator pauses the bonus refresh and clearance scrape
- **THEN** the credential upkeep schedule keeps running

#### Scenario: Fresh deployment

- **WHEN** the stack starts with no stored scheduler state
- **THEN** the credential upkeep schedule is active, like every other schedule

#### Scenario: Upkeep is cheap enough to serialise

- **WHEN** credential upkeep falls due while a data pipeline run is executing
- **THEN** it queues and runs afterwards without materially delaying either
