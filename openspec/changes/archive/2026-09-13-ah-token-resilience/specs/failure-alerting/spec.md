## Purpose

Gets an unattended pipeline failure in front of a person quickly, so that a problem which needs manual recovery is discovered in hours rather than whenever someone next happens to open the portal.

## ADDED Requirements

### Requirement: Pipeline failures reach a person

When a scheduled pipeline run fails, the system SHALL send a notification to a configured external channel, identifying which pipeline failed and why.

#### Scenario: A scheduled run fails

- **WHEN** a scheduled pipeline run reaches a failed state
- **THEN** a notification is sent naming the pipeline, the run, and the failure reason

#### Scenario: A run fails after exhausting its retries

- **WHEN** a run fails only after its retry policy is exhausted
- **THEN** one notification is sent for the final failure, not one per attempt

#### Scenario: A run succeeds

- **WHEN** a run completes successfully
- **THEN** no notification is sent

### Requirement: Alerting is optional and never breaks a pipeline

Alerting SHALL be configured through the environment and SHALL be inert when unconfigured. A failure to deliver a notification SHALL NOT fail a pipeline run, and SHALL NOT be required for the test suite to pass.

#### Scenario: No channel is configured

- **WHEN** the alerting configuration is absent
- **THEN** no notification is attempted and nothing fails, so local development and tests need no external service

#### Scenario: The notification channel is unreachable

- **WHEN** a notification cannot be delivered
- **THEN** the delivery failure is logged and the pipeline's own outcome is unchanged

#### Scenario: Tests run offline

- **WHEN** the automated test suite runs
- **THEN** no notification leaves the machine
