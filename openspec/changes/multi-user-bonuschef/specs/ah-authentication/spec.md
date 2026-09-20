# ah-authentication

## ADDED Requirements

### Requirement: Each account authenticates with its own Albert Heijn session

The system SHALL hold an Albert Heijn credential per account, and SHALL use
that account's credential for every request made on that account's behalf.

Clearance is scoped to a store *and* to a member. A shared session would give
a friend bonus prices that are correct and clearance that is really the
operator's, which is the kind of wrong that looks right - the figure is
plausible, the store name is theirs, and only the shelf disagrees.

#### Scenario: A person's clearance is fetched

- **WHEN** clearance is fetched for an account
- **THEN** it is fetched with that account's credential and against that account's store

#### Scenario: An account has no Albert Heijn credential

- **WHEN** an account has not connected an Albert Heijn login
- **THEN** bonus prices are still shown, clearance is withheld, and the reason is stated rather than left as an empty section

#### Scenario: One account's session expires

- **WHEN** one account's refresh token stops working
- **THEN** only that account is affected, the others continue, and no other account's credential is used in its place

#### Scenario: An account's credential is exercised to keep it alive

- **WHEN** credentials are exercised on a schedule so that disuse does not expire them
- **THEN** every account's credential is exercised, each outcome is reported separately, and one failure neither hides nor causes another

### Requirement: A stored Albert Heijn credential is encrypted at rest

An Albert Heijn refresh token SHALL be encrypted before storage, with a key
that is not held in the database. It SHALL NOT be written to logs, run
output, or any diagnostic surface.

A refresh token is a live session to somebody else's shop account - their
orders, their address, their bonuskaart. The project already treats its own
token this way; holding other people's raises the stake rather than changing
the rule.

#### Scenario: The database is read without the key

- **WHEN** the accounts table is read by someone without the encryption key
- **THEN** no Albert Heijn session can be reconstructed from it

#### Scenario: A token appears in an error

- **WHEN** an Albert Heijn request fails and is reported
- **THEN** the report contains no part of the credential that made it

### Requirement: A person can see and revoke what is held about their shop account

The portal SHALL tell a person what Albert Heijn data is stored about them and
SHALL let them disconnect it, deleting the stored credential.

Someone lending their supermarket account to a friend's hobby project is
entitled to know what that means and to end it without asking.

#### Scenario: A person looks at their connection

- **WHEN** a person opens their account settings
- **THEN** they are told that an Albert Heijn session is held, what it is used for, and when it was last used

#### Scenario: A person disconnects

- **WHEN** a person disconnects their Albert Heijn account
- **THEN** the stored credential is deleted, clearance stops being fetched for them, and their recipes and saved lists are untouched
