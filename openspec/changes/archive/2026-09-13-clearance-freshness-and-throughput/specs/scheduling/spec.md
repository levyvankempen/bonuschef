## ADDED Requirements

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
