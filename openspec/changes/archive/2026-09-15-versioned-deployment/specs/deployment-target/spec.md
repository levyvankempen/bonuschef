## ADDED Requirements

### Requirement: A running deployment states which version it runs

A running deployment SHALL be able to report the version it is running,
without reading source inside a container or comparing files by eye.

The version SHALL be visible to the person using the portal, because the
question "is the fix live?" is usually asked by them rather than by an
operator with a shell.

#### Scenario: Asking what is deployed

- **WHEN** someone wants to know which version is running
- **THEN** the running deployment tells them

#### Scenario: A deployment that was never updated

- **WHEN** a release is cut but the deployment has not been updated
- **THEN** the deployment still reports the older version it actually runs, rather than the newest one that exists

### Requirement: What is deployed is a released version

The documented way to deploy SHALL take a released version and deploy that.
It SHALL NOT copy a working tree, because a working tree can hold changes
that are uncommitted, unpushed, or untested, and nothing about the result
records which.

#### Scenario: Deploying a release

- **WHEN** an operator deploys
- **THEN** they name a released version, and that is what runs

#### Scenario: A deployment host holds no history

- **WHEN** the deployment procedure is followed
- **THEN** the host can be asked which version it holds, rather than being a directory of files with no provenance
