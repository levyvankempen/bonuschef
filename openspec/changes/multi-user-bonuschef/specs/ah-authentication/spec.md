# ah-authentication

## ADDED Requirements

### Requirement: Clearance is fetched per store, with one credential

Clearance SHALL be fetched for each distinct store the accounts use, and MAY
be fetched with a single credential rather than one per account.

Measured on 2026-09-20: `bargainItems` is scoped to the store it is asked
for and gated on authentication, not varied by the member asking. One
credential returned 217 items for Driebergen, 183 for Doorn and 242 for
Zeist, none of them the operator's own store's 90.

This is written down as a requirement because the opposite was assumed for
long enough to justify a design around it. Per-user credentials would have
meant holding other people's supermarket sessions - encrypted at rest, with a
rotation story, a revocation surface, and a connect flow that required
copying an authorization code out of desktop DevTools. None of that buys
correctness, so none of it is built.

#### Scenario: Two accounts choose different stores

- **WHEN** clearance is fetched for accounts whose stores differ
- **THEN** each store's own clearance is fetched, and neither account is shown the other's

#### Scenario: Two accounts choose the same store

- **WHEN** two accounts use one store
- **THEN** that store is fetched once and serves both

#### Scenario: A store has no clearance

- **WHEN** a store returns no clearance items
- **THEN** that is presented as an answer rather than as a failure, because a store legitimately has none

#### Scenario: The assumption stops holding

- **WHEN** a store's fetch returns another store's contents, or is refused for a store that is not the credential's own
- **THEN** it is surfaced rather than stored, because the measurement this design rests on would have gone stale
