## Purpose

Defines what the machine hosting BonusChef must provide for it to run unattended: enough capacity to do its work without displacing what already runs there, a startup path that needs no human, reachability for the person who uses it, and a recovery story for the state that cannot be rebuilt from the repository.

## ADDED Requirements

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

The stack's interfaces SHALL be reachable by their intended user from their own devices, and SHALL NOT be exposed to the wider network or the internet. Neither interface authenticates its callers and one can start and terminate pipeline runs.

#### Scenario: Reaching the portal from a phone

- **WHEN** the intended user opens the portal from a device they own
- **THEN** it is reachable through the documented access path

#### Scenario: Another device on the same network

- **WHEN** an unrelated device on the local network attempts to reach the interfaces directly
- **THEN** the connection is refused

#### Scenario: Exposure to the internet

- **WHEN** the deployment is complete
- **THEN** no interface is published to the internet, directly or by port forwarding
