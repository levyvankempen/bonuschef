## ADDED Requirements

### Requirement: The portal reports the health of the pipeline behind it

The portal SHALL show whether the work that produces its answers is still running, and SHALL say so when it is not. It SHALL NOT rely solely on the age of the source data, because a load that succeeds followed by a rebuild that fails leaves the source fresh and every answer frozen.

#### Scenario: A scheduled job stops succeeding

- **WHEN** a job that feeds the page has not succeeded within the period it runs on
- **THEN** the page says so, naming the job and when it last worked

#### Scenario: Everything is running

- **WHEN** every job is succeeding on its cadence
- **THEN** nothing is shown, because a health indicator that is always present is furniture

#### Scenario: The credential is the one that stopped

- **WHEN** the job that keeps the retailer credential alive has not succeeded recently
- **THEN** that is surfaced distinctly, because its recovery needs a browser and cannot be done unattended

#### Scenario: The warning does not depend on an alerting channel

- **WHEN** no notification channel is subscribed
- **THEN** the page still reports the failure, because it is then the only surface on which it can be noticed
