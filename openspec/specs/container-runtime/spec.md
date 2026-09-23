# container-runtime Specification

## Purpose

Defines how the BonusChef deployment behaves as a long-running service on an always-on host: whether it recovers by itself, how much disk its logs may consume, which interfaces its published ports answer on, how an operator learns a service is unhealthy, and whether a configuration change actually reaches a running deployment.

## Requirements

### Requirement: Services recover without operator action

Every service in the stack SHALL declare a restart policy that brings it back after a host reboot or a non-deliberate exit. An operator's deliberate stop SHALL NOT be undone by that policy.

#### Scenario: Host reboots

- **WHEN** the host running the stack reboots and its container runtime starts
- **THEN** every service of the stack starts again without an operator running any command

#### Scenario: A single container crashes

- **WHEN** one service exits with a non-zero status while the host stays up
- **THEN** that service is started again

#### Scenario: Operator stops the stack on purpose

- **WHEN** an operator stops the stack explicitly
- **THEN** the services stay stopped until the operator starts them again

#### Scenario: Services start in an arbitrary order after a reboot

- **WHEN** the stack is brought back by restart policy rather than by an operator command, so declared start-up ordering does not apply
- **THEN** each service still reaches a working state once its dependencies are available, without an operator intervening

### Requirement: Log growth is bounded

Every service in the stack SHALL cap the disk its own logs occupy, bounding both the size of a single log file and the number of retained rotated files. No service SHALL be able to grow its logs without limit.

#### Scenario: A service logs continuously for months

- **WHEN** a service writes log output continuously over a long unattended period
- **THEN** the disk that service's logs occupy stays within its configured bound, with older output discarded first

#### Scenario: Pipeline history outlives rotated output

- **WHEN** a service's container log output has rotated away
- **THEN** the recorded history of pipeline runs is still retrievable, because it is not stored in container log output

### Requirement: Published ports are reachable only from the host

Every port the stack publishes SHALL bind to the host loopback interface only. This covers the database and both web interfaces.

The portal now authenticates its callers, and the rule is unchanged by that. The Dagster interface still does not, and it can start and terminate pipeline runs; the database has no business being reachable at all. Exposure stays limited to the host, and access from elsewhere stays an operator's explicit decision — a tunnel or an overlay network — rather than a default.

Stated because the reasoning is the part that erodes: a sign-in wall invites the argument that the loopback binding is now redundant, and it is not. One interface gaining a door does not put one on the others.

#### Scenario: Another machine on the network connects to a published port

- **WHEN** a host other than the one running the stack opens a connection to any published port
- **THEN** the connection is refused

#### Scenario: A process on the stack host connects to a published port

- **WHEN** a process on the host running the stack connects to a published port over loopback
- **THEN** the connection succeeds, so local tooling and one-off maintenance keep working

#### Scenario: An operator reaches a web interface from a laptop

- **WHEN** an operator connects from another machine through a tunnel or overlay network that terminates on the stack host
- **THEN** the web interface is reachable, because the traffic arrives over loopback

#### Scenario: Services reach each other internally

- **WHEN** a service connects to another service over the stack's internal network by service name
- **THEN** the connection succeeds, because internal traffic does not depend on a published port

### Requirement: Web-facing services report their health

Each service that serves HTTP SHALL expose a health signal that is polled on an interval, so that an unhealthy service is distinguishable from a healthy one by an operator or an external monitor. Recovering from an unhealthy state is out of scope: a restart policy reacts to a service exiting, not to its health signal, so a wedged-but-running service SHALL be reported rather than restarted.

#### Scenario: A web service is serving normally

- **WHEN** a healthy HTTP service is polled
- **THEN** it reports healthy within its configured timeout

#### Scenario: A web service stops answering

- **WHEN** an HTTP service fails its health probe for the configured number of consecutive attempts
- **THEN** that service is reported as unhealthy, and stays running so an operator can inspect it

#### Scenario: A service is still starting up

- **WHEN** an HTTP service has started but has not finished initialising
- **THEN** its start-up period is not counted as failure, so a slow start does not produce a false alarm

#### Scenario: The database is unavailable

- **WHEN** the database is down but an HTTP service is itself serving
- **THEN** that service still reports healthy, because its health signal describes the service and not its dependencies

#### Scenario: A health probe runs with no outbound access

- **WHEN** a health probe executes
- **THEN** it succeeds using only what the service image already contains, reaching nothing on the network other than the service it polls

### Requirement: Configuration changes reach a running deployment

A change to a configuration file kept in version control SHALL take effect on the next redeploy of the stack. A configuration file SHALL NOT be able to become permanently stale relative to the repository while the deployment keeps running.

#### Scenario: A tracked configuration file is edited and redeployed

- **WHEN** a configuration file is edited in the repository and the stack is redeployed on a host where it has run before
- **THEN** the running services use the edited file

#### Scenario: Persistent data survives a redeploy

- **WHEN** the stack is redeployed
- **THEN** data the services have accumulated is preserved, so configuration freshness is not bought by discarding state

### Requirement: A deployment can be configured from the repository alone

The repository SHALL document every environment variable the services require, with placeholder values and no real secrets. No credential SHALL be committed as a working default.

#### Scenario: First deployment on a new host

- **WHEN** an operator clones the repository onto a new host and follows the documented setup
- **THEN** they can produce a complete environment file without inspecting the service definitions to discover which variables exist

#### Scenario: A required secret is missing

- **WHEN** the stack is started with a required credential absent from the environment
- **THEN** startup fails and names what is missing, rather than silently starting with a well-known default value

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

### Requirement: An image carries the version it was built from

A built image SHALL record the version and the commit it was built from,
where both a running container and an operator inspecting the image can read
them. An image built from a working tree with uncommitted or unpushed changes
SHALL say so rather than claiming the version it is closest to.

#### Scenario: An image built from a released tag

- **WHEN** an image is built from a checkout at a released tag
- **THEN** it reports that version and that commit

#### Scenario: An image built from a modified tree

- **WHEN** an image is built from a checkout carrying changes that are not committed
- **THEN** what it reports marks it as such, so it is not mistaken for the release it resembles

#### Scenario: Inspecting an image without running it

- **WHEN** an operator inspects a built image
- **THEN** the version and commit are readable from its metadata
