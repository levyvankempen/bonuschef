## ADDED Requirements

### Requirement: Choosing a shop the system has not seen starts fetching it

Where a person selects a shop for which the warehouse holds no scraped data,
the portal SHALL start the work that fetches it rather than waiting for the
schedule, and SHALL say that it is running.

Where the shop has already been scraped, the portal SHALL NOT start anything:
the data is already held, and a run per selection would let a person queue work
by changing a dropdown. Runs are serialised for the whole instance, so that
work would be held against the scrape that is actually due.

A failure to start SHALL NOT fail the selection. The shop is the person's
choice and is saved regardless; only the promise about when data arrives
changes.

#### Scenario: The first person to pick a shop

- **WHEN** a person selects a shop the warehouse has never scraped
- **THEN** the scrape is started, and they are told it is running and that the page will fill in

#### Scenario: A shop somebody already uses

- **WHEN** a person selects a shop that has already been scraped
- **THEN** nothing is started, because the data is already held

#### Scenario: Changing back and forth

- **WHEN** a person changes their shop repeatedly between shops that have been scraped
- **THEN** no work is queued by doing so

#### Scenario: The scheduler cannot be reached

- **WHEN** the work cannot be started
- **THEN** the shop is still saved, and the person is told the data will appear on the next scheduled scrape rather than being told the save failed

#### Scenario: What the person is told while it runs

- **WHEN** the scrape has been started for a new shop
- **THEN** the message says the koopjes are being fetched, rather than the page silently showing none
