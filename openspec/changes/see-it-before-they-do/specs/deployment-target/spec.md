## ADDED Requirements

### Requirement: A change can be watched running before the invited people see it

There SHALL be an environment, separate from the one the invited people use,
in which a change can be exercised against realistic data before it reaches
them.

Separate means its own database and its own processes. A flag on the
production deployment that reveals unfinished work to some accounts is not
this: the code is still the code the invited people are running, and a defect
in it reaches them whether or not the flag hides the feature.

Realistic means a copy of production's data rather than a fixture. The defects
this is meant to catch are the ones that only appear against the real
catalogue - a recipe whose ingredient matched nothing, a store with no
markdowns today, a price that is wrong rather than missing - and a seeded
handful of rows reproduces none of them.

#### Scenario: Watching a change before it is released

- **WHEN** a change is merged and an operator wants to see it work
- **THEN** it can be run in the second environment, against a copy of production's data, without the invited people's deployment being touched

#### Scenario: A defect found there does not reach the invited people

- **WHEN** a change turns out to be broken in the second environment
- **THEN** production is still running the previous version, because nothing was promoted

#### Scenario: Fixtures are not a substitute

- **WHEN** the second environment's data is prepared
- **THEN** it is a copy of production's tables, not a hand-written fixture set, so that a recipe priced wrong against the real catalogue is visible before release

#### Scenario: Not a flag on production

- **WHEN** an operator proposes to test by hiding the change behind a setting in the production deployment
- **THEN** that does not satisfy this requirement, because the invited people are running the changed code either way

### Requirement: The second environment never holds the retailer credential

The second environment SHALL NOT hold the member credential, SHALL NOT run the
jobs that call the retailer, and SHALL NOT be able to acquire a credential by
configuration.

This is a hard rule rather than a default, for two independent reasons.

Refreshing the credential may rotate it: the refresh response can carry a new
refresh token, and the stored one is replaced when it does. Two environments
refreshing the same credential would therefore invalidate each other's, and
the failure arrives as prices quietly ceasing to update in whichever
environment refreshed first - which would be production about half the time.

And the load is on someone else's private interface. A second environment
polling it doubles that load for no benefit the first does not already
provide, and the project's own position is that this access is a courtesy
rather than an entitlement.

#### Scenario: The scheduled jobs are absent rather than idle

- **WHEN** the second environment is deployed
- **THEN** the jobs that call the retailer are not present in it, rather than present and disabled by a schedule that someone can switch on

#### Scenario: No credential is configured

- **WHEN** the second environment's configuration is prepared
- **THEN** it carries no member credential, and starting without one is a normal state rather than a failure it reports

#### Scenario: Its data goes stale and that is correct

- **WHEN** the second environment has been running for a week without a refresh
- **THEN** its prices are a week old, it says so by the same freshness vocabulary the portal already uses, and that is not treated as a fault

#### Scenario: Refreshing the copy does not involve the retailer

- **WHEN** an operator wants current data in the second environment
- **THEN** they take a new copy from production, which already holds it, rather than fetching it again

### Requirement: The second environment is not published

The second environment SHALL be reachable only from the host and from the
operator's private network. It SHALL NOT be served to the internet, and
publishing production SHALL NOT publish it as a side effect.

Unfinished work is what it exists to hold. An address that serves it is an
address that serves half-built features and whatever data the last copy
brought, to anybody who has the link.

#### Scenario: Reachable by the operator

- **WHEN** the operator opens the second environment from their own device on their private network
- **THEN** it is reachable, and the documented path says how

#### Scenario: Not reachable from the internet

- **WHEN** the second environment is deployed
- **THEN** no internet-facing address serves it, and no port is forwarded to it

#### Scenario: Publishing production leaves it unpublished

- **WHEN** production's published address is established or renewed
- **THEN** the second environment remains unreachable from outside, rather than inheriting publication from sharing a host

#### Scenario: An invited person cannot find it

- **WHEN** a person who has a production account tries the published address
- **THEN** they reach production, and nothing in what they reach discloses that a second environment exists or how to reach it

### Requirement: The second environment cannot write to production's data

The second environment SHALL connect only to its own database. Its
configuration SHALL make production's database unreachable from it rather than
merely unused by it.

An environment for trying things out is one in which destructive commands get
run, and the worst outcome available here is a schema change or a truncation
that lands on the data the invited people's accounts live in.

#### Scenario: Its own database

- **WHEN** the second environment starts
- **THEN** it connects to its own database instance, with its own credentials

#### Scenario: Production's database is not reachable from it

- **WHEN** something in the second environment attempts to reach production's database
- **THEN** it cannot, because the connection is not available to it rather than merely not configured

#### Scenario: A destructive command is survivable

- **WHEN** the second environment's database is dropped, truncated or migrated wrongly
- **THEN** production is unaffected, and recovery is taking another copy

#### Scenario: Copying runs one way

- **WHEN** data is copied between the environments
- **THEN** it moves from production to the second environment and never the other way

### Requirement: Each environment says which one it is

A running deployment SHALL state which environment it is, in the interface,
wherever it is not production.

The two look identical: the same portal, the same data, the same recipes. A
screenshot, a bug report, or a price checked before leaving the house is
worthless if nobody can tell which deployment produced it - and an operator
who believes they are looking at the second environment will eventually act on
production.

#### Scenario: The second environment is marked

- **WHEN** someone opens the second environment
- **THEN** the interface says so, visibly and on every page, rather than only in a configuration file

#### Scenario: Production carries no marking

- **WHEN** an invited person opens production
- **THEN** they see no environment marker, because for them there is only one and naming it would be noise

#### Scenario: The marker is not only the version

- **WHEN** the two environments run the same released version
- **THEN** they are still distinguishable, because the version does not identify the environment

### Requirement: The copy is taken on request and is identifiable as a copy

Copying production's data into the second environment SHALL be a documented
single command, repeatable, and SHALL NOT require production to stop serving.

The copy SHALL record when it was taken, and the second environment SHALL be
able to say so.

#### Scenario: Taking a copy

- **WHEN** the operator wants current data in the second environment
- **THEN** one documented command produces it, and production keeps serving throughout

#### Scenario: Taking another copy over an existing one

- **WHEN** a copy is taken into an environment that already has data
- **THEN** it replaces it, and the result is the same as copying into an empty one

#### Scenario: Knowing how old the copy is

- **WHEN** an operator is looking at the second environment
- **THEN** they can tell when its data was copied, so that a stale observation is not mistaken for a defect

#### Scenario: The copy lives on the slower disk

- **WHEN** the second environment's database and the stored copies are placed
- **THEN** they are on the bulk disk, so that production's database keeps the fast one to itself

## MODIFIED Requirements

### Requirement: What is deployed is a released version

The documented way to deploy SHALL take a released version and deploy that.
It SHALL NOT copy a working tree, because a working tree can hold changes
that are uncommitted, unpushed, or untested, and nothing about the result
records which.

Where a second environment exists, what reaches production SHALL be the
artifact that was watched running there, identified the same way in both.
Rebuilding from the same commit SHALL NOT be treated as equivalent: a rebuild
can differ from what was watched by anything not pinned, and the point of
watching it was to know what production is about to run.

#### Scenario: Deploying a release

- **WHEN** an operator deploys
- **THEN** they name a released version, and that is what runs

#### Scenario: A deployment host holds no history

- **WHEN** the deployment procedure is followed
- **THEN** the host can be asked which version it holds, rather than being a directory of files with no provenance

#### Scenario: Promoting what was watched

- **WHEN** a version has been exercised in the second environment and is promoted
- **THEN** production runs that same artifact, identified by the same version, rather than one rebuilt from its source

#### Scenario: Promoting something that was never watched

- **WHEN** a version is deployed to production without having run in the second environment
- **THEN** that is available and recorded as such, because an urgent fix must not wait on a second environment that happens to be broken
