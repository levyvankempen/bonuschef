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
