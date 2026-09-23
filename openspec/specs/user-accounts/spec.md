# user-accounts Specification

## Purpose
Who is using bonuschef, and which of the data they see is theirs. The system
was built for one person and one store; this capability is what makes a second
person's prices, recipes and shop account distinct from the first person's.

## Requirements

### Requirement: A person signs in before seeing anything

The portal SHALL require an authenticated session before rendering any page
that reads data, and SHALL present only the sign-in page to an unauthenticated
visitor.

There is no anonymous view worth keeping. Every page either shows prices
scoped to a store, or recipes scoped to a person, and both are now per-user.

#### Scenario: An unauthenticated visitor opens any page

- **WHEN** someone without a session opens the portal at any address within it
- **THEN** they are shown the sign-in page and no data from any other page

#### Scenario: A signed-in person moves between pages

- **WHEN** an authenticated person navigates the portal
- **THEN** they are not asked to sign in again for the life of their session

#### Scenario: A session outlives its usefulness

- **WHEN** a session has been idle beyond its lifetime
- **THEN** it stops being accepted, and the person signs in again rather than silently seeing another state

### Requirement: Accounts are created by invitation, not by open signup

The system SHALL NOT offer self-service registration. An account SHALL be
created only by an operator action.

An open signup form on an application that stores other people's Albert Heijn
sessions is a liability with no upside at this size. The intended users are a
handful of friends who can be told their password directly.

#### Scenario: A stranger finds the sign-in page

- **WHEN** someone without an account reaches the portal
- **THEN** there is no route to create one, and nothing reveals whether a given username exists

#### Scenario: The operator adds a friend

- **WHEN** the operator creates an account with a username and an initial password
- **THEN** that person can sign in, and is required to set their own password before anything else

### Requirement: A password is stored so that the database does not reveal it

Passwords SHALL be stored only as the output of a deliberately slow,
salted password hash. The system SHALL NOT store, log, or transmit a password
in a form from which it can be recovered.

This is stated as a requirement rather than left to implementation because the
failure is silent: a fast hash looks identical in every test and differs only
when the database is read by someone who should not have it.

#### Scenario: The database is read by someone who should not have it

- **WHEN** an attacker obtains the accounts table
- **THEN** the passwords are not recoverable from it in reasonable time, and no two identical passwords appear identical

#### Scenario: A sign-in attempt fails

- **WHEN** a password does not match
- **THEN** the response does not distinguish a wrong password from an unknown username, and the attempt is recorded

#### Scenario: Someone tries many passwords

- **WHEN** repeated failures accumulate against one account
- **THEN** further attempts are slowed or refused, rather than answered at full speed indefinitely

### Requirement: A store belongs to a person

Each account SHALL carry its own Albert Heijn store, and every price the
portal shows that depends on a store SHALL be that person's store.

`AH_STORE_ID` is currently an environment variable read once at startup.
Clearance is scoped to a store and to a member, so two users with different
stores do not have a preference difference - they have different prices.

#### Scenario: Two people with different stores look at the same recipe

- **WHEN** two signed-in people open the same recipe
- **THEN** each sees the clearance prices of their own store, and neither sees the other's

#### Scenario: A person has not chosen a store

- **WHEN** an account has no store set
- **THEN** they are asked to choose one, and clearance-dependent figures are withheld rather than filled in from someone else's store

#### Scenario: A person changes their store

- **WHEN** a person sets a different store
- **THEN** subsequent figures reflect the new store, and nothing from the previous one is presented as current

### Requirement: What is personal is not visible to other accounts

Data recorded against an account - its saved recipes, edits, notes, last-made
dates, store and credentials - SHALL be readable only by that account.

#### Scenario: One person saves a recipe

- **WHEN** a person saves a recipe to their collection
- **THEN** no other account's collection changes, and no other account can see that they saved it

#### Scenario: One person annotates a shared recipe

- **WHEN** a person edits or annotates a recipe from the shared catalogue
- **THEN** every other account continues to see the recipe as it was

#### Scenario: Two accounts use the portal at the same time

- **WHEN** two accounts read the same account-scoped or store-scoped view from one running portal
- **THEN** each is served its own data, and neither is served a value computed for the other

#### Scenario: One person rejects a recipe

- **WHEN** a person marks a recommended recipe as not for them
- **THEN** it stops being recommended to them and continues to be recommended to everybody else

#### Scenario: One person adopts a recipe

- **WHEN** a person adopts a recipe from the pool of recommendations
- **THEN** it remains available for every other account to be recommended and to adopt
