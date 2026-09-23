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

### Requirement: Independent models build in parallel within a run

Within a single pipeline run, models with no dependency on one another SHALL be built concurrently. Parallelism within a run is distinct from concurrency between runs: runs are serialised to keep two pipelines from racing on the same tables, which SHALL NOT be read as a reason to build one model at a time inside a run.

#### Scenario: A full rebuild with independent models

- **WHEN** a run rebuilds a model set whose members have no interdependencies
- **THEN** those models are built concurrently rather than strictly one after another

#### Scenario: Dependent models

- **WHEN** one model depends on another
- **THEN** the dependency is still built first; parallelism never violates the dependency order

#### Scenario: Parallelism is bounded

- **WHEN** models are built concurrently
- **THEN** the number built at once is bounded, so a rebuild cannot exhaust the database's connections or the host's CPU

#### Scenario: Run serialisation is unaffected

- **WHEN** within-run parallelism is increased
- **THEN** two separate runs still do not execute at the same time
