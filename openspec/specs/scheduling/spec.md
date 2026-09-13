# scheduling Specification

## Purpose

Defines when each BonusChef pipeline runs unattended, in which timezone, whether it is active on a fresh deployment, and whether two runs may execute at the same time — so that data lands at times matching how Albert Heijn publishes it, without runs colliding in the warehouse.

## Requirements

### Requirement: The bonus refresh runs once daily in the late afternoon

The pipeline that refreshes the AH bonus feed and rebuilds every downstream model SHALL be scheduled once per day at 17:30 Dutch local time.

#### Scenario: The scheduled time arrives

- **WHEN** the clock reaches 17:30 Dutch local time
- **THEN** exactly one bonus refresh run is requested

#### Scenario: Any other time of day

- **WHEN** the clock reaches any time other than 17:30 Dutch local time
- **THEN** no bonus refresh run is requested

### Requirement: The clearance scrape runs hourly through the afternoon

The pipeline that scrapes store clearance ("laatste kans koopjes") markdowns SHALL be scheduled once per hour from 11:00 through 20:00 Dutch local time. The intraday sequence of runs is what records how a markdown deepens over a day, so the cadence SHALL NOT be reduced to a single daily run.

#### Scenario: Afternoon hours

- **WHEN** the clock reaches the top of any hour from 11:00 through 20:00 Dutch local time
- **THEN** one clearance scrape run is requested for that hour

#### Scenario: Overnight hours

- **WHEN** the clock reaches the top of an hour outside 11:00 through 20:00 Dutch local time
- **THEN** no clearance scrape run is requested, because the store publishes no markdowns then

### Requirement: Schedules follow Dutch local time across daylight saving

Every schedule SHALL be evaluated in the Europe/Amsterdam timezone, so a scheduled wall-clock time keeps its relationship to store opening hours on both sides of a daylight-saving transition, whatever the host's own timezone.

#### Scenario: Winter and summer

- **WHEN** a schedule is due at a given local time in winter, and again at the same local time in summer
- **THEN** both runs start at that local wall-clock time, despite the differing UTC offset

#### Scenario: The host runs in a different timezone

- **WHEN** the host executing the pipelines has a system timezone other than Europe/Amsterdam
- **THEN** schedules still fire at Dutch local time

### Requirement: Automation is active on a fresh deployment

Every schedule and every sensor SHALL be enabled by default, so that a deployment with no prior scheduler state begins running its pipelines without an operator enabling anything by hand.

#### Scenario: First start on a new host

- **WHEN** the stack starts with no stored scheduler state
- **THEN** every schedule and sensor is active, and the next due run is requested without operator action

#### Scenario: Nothing is silently idle

- **WHEN** an operator inspects a freshly deployed stack
- **THEN** no schedule or sensor is found in a disabled state that would have to be discovered before data stopped arriving

### Requirement: Pipeline runs do not execute concurrently

At most one pipeline run SHALL execute at a time; further runs SHALL queue and execute in turn rather than being dropped. The bonus refresh rebuilds every downstream model, a superset of what the clearance scrape rebuilds, and the shared warehouse setup is not safe to execute twice at once — so overlapping schedules MUST serialise rather than race.

#### Scenario: A scheduled run is due while another is still executing

- **WHEN** a run becomes due while a previous run has not finished
- **THEN** the new run is queued and starts once the running one completes, and is not discarded

#### Scenario: The daily rebuild overruns into a clearance slot

- **WHEN** the bonus refresh is still rebuilding models at the time an hourly clearance scrape falls due
- **THEN** both runs complete successfully, one after the other, with neither failing on contention for the same tables

#### Scenario: An on-demand run is requested from the portal

- **WHEN** an operator triggers a refresh from the portal while a scheduled run is executing
- **THEN** the requested run is accepted and reported as pending rather than rejected, and executes once the warehouse is free

### Requirement: A failed scheduled run is retried

Every scheduled pipeline SHALL retry a failed run before giving up, so a transient failure — a queued run meeting a busy warehouse, or a briefly unavailable upstream API — does not silently skip a day's data.

#### Scenario: A run fails transiently

- **WHEN** a scheduled run fails for a transient reason
- **THEN** it is retried after a delay, and a subsequent success leaves the data complete for that slot

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
