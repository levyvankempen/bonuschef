## Purpose

Keeps member access to the Albert Heijn API alive on an unattended host: persisting and rotating credentials safely, refreshing them on a cadence that does not depend on any single consumer succeeding, and reporting enough about their state to tell a credential that is expiring from one that is merely unused.

## ADDED Requirements

### Requirement: Credential liveness does not depend on any one consumer

The system SHALL refresh its stored member credentials on a schedule of its own, independently of whether any data pipeline runs or succeeds. A pipeline failing for an unrelated reason SHALL NOT cause the credentials to lapse as a side effect.

#### Scenario: Every data pipeline is failing

- **WHEN** the pipelines that consume the AH API have been failing for days for a reason unrelated to authentication
- **THEN** the stored credentials are still refreshed on their own cadence, so the outage stays recoverable without an interactive login

#### Scenario: Refresh cadence outpaces credential lifetime

- **WHEN** the system is running normally
- **THEN** credentials are refreshed more often than they would lapse from disuse, with margin for a missed cycle

#### Scenario: The upkeep refresh itself fails

- **WHEN** a scheduled credential refresh cannot obtain a valid token
- **THEN** it fails loudly rather than silently, so the failure is reportable

### Requirement: A rotated credential is never lost

When the provider issues a replacement refresh credential, the system SHALL persist the replacement before relying on it, and SHALL survive the case where a concurrent process rotated the credential first.

#### Scenario: The provider returns a new refresh credential

- **WHEN** a refresh response carries a replacement refresh credential
- **THEN** the replacement is stored, and the next refresh uses it rather than the superseded one

#### Scenario: The provider returns no new refresh credential

- **WHEN** a refresh response omits a replacement
- **THEN** the credential that was used remains stored and usable

#### Scenario: Another process rotated first

- **WHEN** a refresh is attempted with a credential another process has already replaced
- **THEN** the system retries with the most recently stored credential before declaring failure

#### Scenario: Interrupted while writing

- **WHEN** the process is interrupted while persisting a credential
- **THEN** the stored credential is left either wholly the old one or wholly the new one, never a partial write

### Requirement: Credential state is observable

Each refresh SHALL record whether the provider rotated the refresh credential, and how long the credential in use had been stored. This distinguishes a provider that extends a credential's life on use from one that expires it on a fixed clock — which determines whether interactive re-authentication can be eliminated or only made rare.

#### Scenario: A refresh succeeds

- **WHEN** a credential refresh completes successfully
- **THEN** the run records whether the refresh credential changed, and the age of the one that was used

#### Scenario: Accumulating evidence over time

- **WHEN** refreshes have run for several cycles
- **THEN** the recorded history is sufficient to determine whether the provider rotates on every refresh, and the greatest age a credential has reached while still working

### Requirement: Credentials outlive the processes that use them

Stored credentials SHALL survive rebuilding or replacing the processes that use them, and SHALL be readable by every process that needs them.

#### Scenario: The deployment is rebuilt

- **WHEN** the application containers are rebuilt and recreated
- **THEN** the previously stored credentials are still present and usable, with no interactive login required

#### Scenario: Credentials are stored at rest

- **WHEN** credentials are written to disk
- **THEN** they are readable only by the owning user

### Requirement: An unrecoverable credential failure is explicit

When every known credential has been rejected, the system SHALL fail with a message naming the interactive step required to recover and where the credentials are stored. It SHALL NOT retry indefinitely, and SHALL NOT degrade to returning no data as though the source were empty.

#### Scenario: Every stored credential is rejected

- **WHEN** all known refresh credentials are rejected by the provider
- **THEN** the failure message names the re-authentication command and the credential location

#### Scenario: A rejected credential is not mistaken for an empty result

- **WHEN** authentication fails
- **THEN** the consuming pipeline fails, rather than recording an empty snapshot that would read as "no clearance items today"
