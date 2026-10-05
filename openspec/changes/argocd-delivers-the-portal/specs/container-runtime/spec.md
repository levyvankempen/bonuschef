## ADDED Requirements

### Requirement: The application's desired state lives in the repository

Where the application is delivered by a cluster, what should be running SHALL
be described in the repository, and the cluster SHALL reconcile toward that
description without an operator applying it.

A commit that changes the description SHALL be enough to change what runs. No
step SHALL require a shell on the cluster for an ordinary release.

The cluster SHALL be able to report what it is converging on and whether it has
got there, so "is the fix live" is answerable without inspecting pods.

#### Scenario: A release is published

- **WHEN** a release changes the described version
- **THEN** the cluster converges on it without an operator applying anything

#### Scenario: Someone changes a running workload by hand

- **WHEN** a workload is edited directly in the cluster
- **THEN** the repository's description wins, because a cluster that honours manual edits has two sources of truth

#### Scenario: Asking what is deployed

- **WHEN** an operator asks what the cluster is running
- **THEN** it reports the described version, whether it has converged, and the difference if it has not

#### Scenario: A described version that cannot be pulled

- **WHEN** the described image tag does not exist
- **THEN** the previously running version keeps serving, and the failure to converge is reported rather than leaving nothing running

### Requirement: An image is built once and pulled thereafter

A cluster SHALL NOT build images. Every workload SHALL run an image published to
a registry and referenced by an immutable tag.

A tag SHALL identify one build. Re-pointing a tag at different content SHALL NOT
be how a change is delivered, because then the described state no longer
determines what runs.

#### Scenario: Delivering a change

- **WHEN** the application changes
- **THEN** a new image is published under a new tag and the description is updated to it

#### Scenario: A workload that would need to build

- **WHEN** a workload has no published image
- **THEN** it is not deployed to the cluster, rather than the cluster acquiring a build step

### Requirement: One workload has one manager

A workload SHALL be managed by exactly one deployment mechanism at a time.

Where delivery moves from one mechanism to another, the mechanism being
replaced SHALL stop managing that workload as part of the move, and the
documented path SHALL say which manages what.

Two mechanisms reconciling toward their own idea of "current" is how a rollback
becomes a fight, and how a deploy succeeds and is then undone a few minutes
later by a timer that disagrees.

#### Scenario: Delivery moves to the cluster

- **WHEN** the cluster takes over a workload
- **THEN** the previous mechanism no longer deploys it

#### Scenario: A workload the cluster does not take

- **WHEN** a workload stays outside the cluster
- **THEN** the documented path says so, and which mechanism owns it

### Requirement: Secrets are referenced by the repository, never carried in it

Where committed configuration needs a credential, it SHALL name the secret and
SHALL NOT contain its value. The values SHALL be supplied to the cluster out of
band.

A chart that renders a usable default credential is worse than one that fails to
start, because the first serves traffic.

#### Scenario: Configuration that needs a credential

- **WHEN** a workload needs a token or a password
- **THEN** the committed configuration refers to a secret by name and holds no value, not even a placeholder that would function

#### Scenario: A secret that has not been supplied

- **WHEN** a named secret is absent from the cluster
- **THEN** the workload does not start, and says which secret is missing

## MODIFIED Requirements

### Requirement: A committed deployment path meets the requirements it is subject to

Deployment configuration committed to the repository SHALL satisfy the same guarantees as the deployment in use, or SHALL NOT be committed. An unmaintained path that breaks the rules reads as a supported one.

This is the requirement that removed this project's previous Kubernetes
manifests: they were committed, unrun, and met none of the guarantees around
them. A cluster path is subject to all of it - recovery without an operator,
bounded logs, interfaces reachable only as permitted, health that reflects
whether a service can do its work, configuration from the repository alone, no
credential in committed configuration, and an image that carries the version it
was built from. Being declarative exempts it from none of them.

#### Scenario: Configuration for a deployment nobody runs

- **WHEN** committed configuration describes a stack that violates the binding requirements
- **THEN** it is removed rather than left to be found and trusted

#### Scenario: Credentials in committed configuration

- **WHEN** deployment configuration is committed
- **THEN** it carries no working credential, not even a placeholder that functions

#### Scenario: A second deployment path is committed

- **WHEN** a deployment path is committed alongside the one in use
- **THEN** it meets every guarantee the one in use meets, and the documented path says which is live
