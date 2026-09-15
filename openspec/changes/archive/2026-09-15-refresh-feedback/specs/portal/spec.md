## MODIFIED Requirements

### Requirement: The portal finishes its own work

Where an action requires pipeline work to take effect, the portal SHALL carry it out and report the outcome. It SHALL NOT instruct the person to run a command elsewhere.

Reporting the outcome SHALL NOT depend on the person's session surviving the work. The state SHALL be read from the run itself, so that a session which was interrupted still learns how it went.

Work that is waiting to start SHALL be distinguishable from work that is running.

#### Scenario: After adding a recipe

- **WHEN** a person adds a recipe whose cost needs computing
- **THEN** the portal starts that work itself and shows the result when it completes

#### Scenario: The work fails

- **WHEN** the pipeline work fails
- **THEN** the failure is shown, and the recipe is not presented as priced

#### Scenario: No instructions to use a terminal

- **WHEN** any action completes
- **THEN** the portal does not ask the person to run a build command by hand

#### Scenario: The work has not started yet

- **WHEN** requested work is waiting behind other work
- **THEN** the page says it is waiting rather than describing it as under way

#### Scenario: The session is interrupted while work runs

- **WHEN** a person leaves the page, or their session drops, before the work finishes
- **THEN** returning to the page reports how the work went, rather than showing no trace of it

#### Scenario: A completed refresh reaches every reader

- **WHEN** pipeline work finishes and changes what a page would show
- **THEN** the page reflects it without waiting for a cache to expire, including for a session that did not request the work

#### Scenario: Success is not confused with change

- **WHEN** requested work completes without altering the data
- **THEN** the page does not claim the data is newer than it is
