## ADDED Requirements

### Requirement: Unattended running does not accumulate hidden state

A stack that runs for months without attention SHALL NOT retain data it has finished with, and SHALL NOT keep operational state where an operator inspecting the host would not find it.

#### Scenario: A completed load

- **WHEN** a load finishes successfully
- **THEN** its intermediate artefacts are not retained, because the disk cost of a load should be the data it loaded

#### Scenario: A failed load

- **WHEN** a load fails
- **THEN** what it was working on is kept, because that is the case where the artefacts are the diagnosis

#### Scenario: State an operator cannot find

- **WHEN** the stack writes operational state that grows over time
- **THEN** it is on a volume, so that inspecting the host reveals it and the backup captures it

### Requirement: A committed deployment path meets the requirements it is subject to

Deployment configuration committed to the repository SHALL satisfy the same guarantees as the deployment in use, or SHALL NOT be committed. An unmaintained path that breaks the rules reads as a supported one.

#### Scenario: Configuration for a deployment nobody runs

- **WHEN** committed configuration describes a stack that violates the binding requirements
- **THEN** it is removed rather than left to be found and trusted

#### Scenario: Credentials in committed configuration

- **WHEN** deployment configuration is committed
- **THEN** it carries no working credential, not even a placeholder that functions
