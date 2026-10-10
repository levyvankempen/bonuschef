## MODIFIED Requirements

### Requirement: The person who uses it can reach it, and nobody else can

The portal MAY be published to the internet so that people the operator has
invited can reach it from their own devices without installing anything. Where
it is, it SHALL be served over HTTPS, and the sign-in wall in front of it SHALL
refuse repeated guessing.

Every other interface SHALL remain unreachable from outside the host. The
Dagster interface above all: it has no authentication and it can start and
terminate pipeline runs, so for that interface the network restriction is not
made redundant by the portal's sign-in wall - it is the only thing protecting
it, and publishing the portal SHALL NOT publish it as a side effect.

Where the application is delivered by a cluster, the same rule binds the
cluster's own interfaces. A delivery tool's console can change what runs and
read what it is configured with, so it SHALL NOT be published, and the cluster
SHALL NOT expose a workload to the internet merely by running it. Only the
portal is published, and it is published deliberately.

Publishing SHALL NOT require exposing the host's own network. A port forwarded
on the router publishes the address of the house along with the application, and
withdrawing it is a manual undo of a manual change.

Publication SHALL be withdrawable, and the documented path SHALL say how.

#### Scenario: Reaching the portal from a phone

- **WHEN** the intended user opens the portal from a device they own
- **THEN** it is reachable through the documented access path

#### Scenario: Another device on the same network

- **WHEN** an unrelated device on the local network attempts to reach the interfaces directly
- **THEN** the connection is refused

#### Scenario: An invited person on someone else's network

- **WHEN** a person the operator has invited opens the published address from outside the home network
- **THEN** the portal is reachable over HTTPS, and they are asked to sign in before seeing anything

#### Scenario: The pipeline interface is not published with it

- **WHEN** the portal is published
- **THEN** the Dagster interface remains bound to the host and is reachable from nowhere outside it

#### Scenario: Exposure to the internet

- **WHEN** the deployment is complete
- **THEN** the portal is the only interface published to the internet, and every other interface is published to it by no route, directly or by port forwarding

#### Scenario: No port is forwarded to reach it

- **WHEN** the portal is published
- **THEN** it is served without a port forwarded on the router and without the home network's address being disclosed

#### Scenario: Taking it down again

- **WHEN** the operator withdraws publication
- **THEN** the address stops serving, the documented path says how, and the local access route is unaffected

#### Scenario: The delivery tool's own console

- **WHEN** the application is delivered by a cluster
- **THEN** the tool that controls what runs is reachable only from the host, because it can change the deployment and read its configuration

#### Scenario: A workload that is not meant to be public

- **WHEN** a workload runs in the cluster without being deliberately published
- **THEN** it is reachable only from the host, rather than becoming public by default

#### Scenario: The published address survives the move

- **WHEN** delivery of the portal moves from one mechanism to another
- **THEN** the address people were given keeps working, because it was shared and cannot be recalled

## ADDED Requirements

### Requirement: The cluster delivers both environments, not just production

Where the application is delivered by a cluster, the cluster SHALL deliver the
test environment as well as production, from one description with per-environment
values.

This change was written when there was one environment. There are two: the test
environment exists, holds a copy of production's data, and is the thing a change
is watched in before anybody else sees it. A cluster that delivers only
production would leave the second environment on the mechanism this change
retires, which is two delivery paths for one application - the exact thing this
change forbids elsewhere.

Every requirement the test environment already carries SHALL continue to hold
under the cluster: it holds no retailer credential, it is not published, it
cannot reach production's database, and it says which environment it is. None of
those is a property of Compose; they are properties of the environment, and the
mechanism changing SHALL NOT quietly drop them.

#### Scenario: A release reaches both environments

- **WHEN** a version is described for an environment
- **THEN** the cluster converges that environment on it, independently of the other

#### Scenario: One description, two sets of values

- **WHEN** the two environments differ
- **THEN** they differ by values rather than by a second copy of the description, so a fix cannot land in one and be forgotten in the other

#### Scenario: The credential rule survives the migration

- **WHEN** the test environment runs under the cluster
- **THEN** it has no retailer credential and no scheduled job that would use one, because the failure that rule prevents is production's prices silently ceasing to update

#### Scenario: The isolation rule survives the migration

- **WHEN** the test environment runs under the cluster
- **THEN** production's database is unreachable from it, and it is served to no internet-facing address

### Requirement: One surface shows what every environment is running and whether it is well

There SHALL be one place that reports, for every environment: the version it is
running, whether it has converged on the version it was asked to run, and
whether it is healthy.

That surface SHALL NOT be one of the environments it reports on. Today it is -
production's operator page reads the test environment's database, over a network
route that exists for no other reason - and that is the wrong shape twice over.
The observer is one of the things being observed, so production being down takes
the view of test down with it. And it required a route between two environments
that are otherwise deliberately unable to reach each other, which is a weakening
of the isolation rule paid for in monitoring.

When this requirement is met, that route and that panel SHALL be removed rather
than left in place beside it. A second way to answer the same question is a
second thing to keep correct, and this one costs isolation to keep.

#### Scenario: Asking after both environments at once

- **WHEN** an operator wants to know the state of the deployment
- **THEN** one surface answers for every environment, without opening either of them

#### Scenario: An environment is down

- **WHEN** one environment is not serving
- **THEN** the surface says so, and remains able to report on the other

#### Scenario: Converged is distinguished from healthy

- **WHEN** an environment is running the version it was asked to run but cannot serve
- **THEN** those are reported as different states, because "the right version is deployed" and "it works" fail independently and have different fixes

#### Scenario: The cross-environment route is retired

- **WHEN** the surface reports on the test environment
- **THEN** production no longer connects to the test environment's database, and the network that allowed it is gone

#### Scenario: Metric history is not what this requires

- **WHEN** this requirement is satisfied
- **THEN** it is satisfied by current state rather than by stored history, because per-container trends answer a different question and the platform's own graphs already cover the host and its guests

