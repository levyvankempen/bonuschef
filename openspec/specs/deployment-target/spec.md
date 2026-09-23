# deployment-target Specification

## Purpose

Defines what the machine hosting BonusChef must provide for it to run unattended: enough capacity to do its work without displacing what already runs there, a startup path that needs no human, reachability for the person who uses it, and a recovery story for the state that cannot be rebuilt from the repository.

## Requirements

### Requirement: The host has capacity for the workload alongside what it already runs

The host SHALL have enough free memory for the stack's measured resident usage plus headroom for its heaviest scheduled work, without displacing existing workloads. Where capacity is insufficient, deployment SHALL be blocked on an explicit decision rather than proceeding into contention.

#### Scenario: Capacity is sufficient

- **WHEN** free memory exceeds the stack's measured need with headroom for a rebuild
- **THEN** the stack is deployed at its normal sizing

#### Scenario: Capacity is insufficient

- **WHEN** free memory does not cover the measured need
- **THEN** deployment stops and states the shortfall in measured terms, rather than provisioning a guest that will swap under load

#### Scenario: An existing workload must not be silently degraded

- **WHEN** capacity is found by reclaiming memory from something already running on the host
- **THEN** that is an explicit decision with its consequence stated, not a side effect of deploying

#### Scenario: Disk for the database and images

- **WHEN** the stack is provisioned
- **THEN** the host has room for the container images, the database and its growth, and the platform's own backups of the guest

### Requirement: The stack starts without a human after a power loss

The host SHALL start its container runtime automatically at boot, and the guest hosting the stack SHALL start automatically with the host. Every restart guarantee the application declares depends on this, and SHALL NOT be assumed.

#### Scenario: The host loses power and returns

- **WHEN** the machine boots after an unexpected power loss
- **THEN** the guest starts, the container runtime starts, and the stack comes back with no one logging in

#### Scenario: The dependency is verified rather than assumed

- **WHEN** deployment completes
- **THEN** the automatic-start path has been exercised, not merely configured

### Requirement: A deployment is reproducible from the repository

Deploying SHALL require only the repository, a configuration file derived from its committed template, and the documented commands. No step SHALL depend on knowledge held only by whoever deployed it the first time.

#### Scenario: Deploying onto a clean host

- **WHEN** an operator follows the documented procedure on a host that has never run the stack
- **THEN** the stack runs, without needing a value or command that is not written down

#### Scenario: Updating a running deployment

- **WHEN** a new version is released
- **THEN** updating is the documented sequence and preserves accumulated data

#### Scenario: Secrets are not in the repository

- **WHEN** configuration is prepared
- **THEN** credentials come from the operator's environment file, and none is committed

### Requirement: State that cannot be rebuilt is identified and recoverable

The deployment SHALL distinguish state that can be rebuilt from the repository and its sources from state that cannot, and SHALL ensure the latter is recoverable. The member API credential and the accumulated price and markdown history SHALL be treated as unrecoverable by rebuild.

#### Scenario: The guest is lost

- **WHEN** the guest is destroyed or corrupted
- **THEN** it can be restored from a backup taken by the platform, including the database and the stored credential

#### Scenario: A derived table is lost

- **WHEN** a warehouse model is dropped
- **THEN** it is rebuilt from source tables by running the pipeline, with no backup needed

#### Scenario: The credential cannot be recreated unattended

- **WHEN** the stored member credential is lost
- **THEN** recovery requires an interactive browser login, and the procedure says so rather than implying it can be automated

#### Scenario: Backups are verified

- **WHEN** a backup schedule is established
- **THEN** at least one restore has been confirmed to produce a working guest

### Requirement: The person who uses it can reach it, and nobody else can

The stack's interfaces SHALL be reachable by their intended users from their own devices, and SHALL NOT be exposed to the wider network or the internet.

The portal authenticates its callers; the Dagster interface does not, and it can start and terminate pipeline runs. So the network restriction is not made redundant by the sign-in wall - it is what stands in front of the interface that still has none, and it remains the only thing protecting it.

#### Scenario: Reaching the portal from a phone

- **WHEN** the intended user opens the portal from a device they own
- **THEN** it is reachable through the documented access path

#### Scenario: Another device on the same network

- **WHEN** an unrelated device on the local network attempts to reach the interfaces directly
- **THEN** the connection is refused

#### Scenario: Exposure to the internet

- **WHEN** the deployment is complete
- **THEN** no interface is published to the internet, directly or by port forwarding

### Requirement: A health signal reflects whether the service can do its work

A service's health SHALL be judged on whether it can serve what it exists to serve, not merely on whether its process is answering. A probe that passes while the service cannot do its job is worse than no probe, because an operator and an automated monitor both trust it.

#### Scenario: The service cannot load what it serves

- **WHEN** a service is running and answering requests, but cannot load the definitions, configuration or content it exists to serve
- **THEN** it reports unhealthy

#### Scenario: A dependency is down

- **WHEN** a service is able to serve its own content but something it depends on is unavailable
- **THEN** it still reports healthy, because the failure is not its own and a cascade of unhealthy services hides where the fault is

#### Scenario: The right shape carrying nothing

- **WHEN** a probe asks a service for something it serves, and the service answers with a well-formed but empty response
- **THEN** the emptiness is treated as failure, because a collection with no members is what a broken service returns and a probe that checks only the shape of an answer has not checked the answer

#### Scenario: A probe is proven, not assumed

- **WHEN** a health probe is introduced or changed
- **THEN** it has been observed to fail for a service that is genuinely broken, rather than only observed to pass for one that is working

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
