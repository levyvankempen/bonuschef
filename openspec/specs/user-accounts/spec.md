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

Registration SHALL require an invitation that the operator issues and can
withdraw. Holding the invitation is what makes someone invited; being told a
password by the operator is one way to issue it, and a shared code the operator
can rotate is another.

Registration SHALL NOT be open. Where no invitation mechanism is configured,
there SHALL be no route to create an account at all.

An open signup form on an application that stores other people's Albert Heijn
sessions is a liability with no upside at this size. The intended users are a
handful of friends, and the operator decides which of them gets in.

The requirement previously said self-service registration SHALL NOT exist and
that a stranger finds no route to create an account. The portal has offered
registration behind an invitation code since accounts became multi-user, so the
requirement described something that had stopped being true - which is worse
than either answer, because it is the text a reader would trust.

#### Scenario: A stranger finds the sign-in page

- **WHEN** someone without an account and without an invitation reaches the portal
- **THEN** they cannot create one, and nothing reveals whether a given username exists

#### Scenario: The operator adds a friend

- **WHEN** the operator creates an account with a username and an initial password
- **THEN** that person can sign in, and is required to set their own password before anything else

#### Scenario: A friend registers with the invitation

- **WHEN** a person holds the operator's current invitation code
- **THEN** they can create an account and are signed in, without the operator doing anything per person

#### Scenario: A wrong invitation code

- **WHEN** a registration is attempted without the current code
- **THEN** it is refused, and the refusal does not reveal whether the chosen username was available

#### Scenario: The invitation is withdrawn

- **WHEN** the operator removes or rotates the invitation
- **THEN** the previous code creates no further accounts, and existing accounts are unaffected

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
dates, store and credentials - SHALL be readable only by that account and by an
operator.

No ordinary account SHALL be able to read another's, by any route.

An operator is the person whose machine the data sits on and who can read the
database directly; a surface that shows it to them creates no access they did
not have. What it does create is the possibility of the code and this text
disagreeing, which is why the exception is written here rather than left
implied.

Credentials remain readable by nobody. A password is stored only as a hash, and
an operator reading the database learns no more from it than anyone else would.

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

#### Scenario: An ordinary account looks for another's data

- **WHEN** an account that is not an operator attempts to reach another account's data by any route the portal offers
- **THEN** it is refused, and the exception made for an operator does not widen to them

#### Scenario: An operator reviews the accounts

- **WHEN** an operator opens the surface that lists accounts
- **THEN** they see each account's activity, store and saved recipes, being able to read the same from the database regardless

#### Scenario: A password is not among what an operator sees

- **WHEN** an operator reviews an account
- **THEN** no password or password hash is displayed, because the exception covers what a person recorded and not the secret that authenticates them

### Requirement: Repeated failed sign-ins are slowed and then refused

Where sign-in is reachable by people the operator has not met, a run of failed
attempts against one account SHALL be slowed, and after a threshold SHALL be
refused outright for a period, regardless of whether the password offered is
correct.

The count SHALL survive a restart of the application. An in-process counter
resets on every deploy, and a deploy is something an attacker can wait for.

A refusal for being locked out SHALL NOT disclose whether the account exists.
The wall's first duty is not to answer the question "is there a levy here",
and a lockout message that only appears for real accounts answers it.

#### Scenario: A run of wrong passwords

- **WHEN** an account receives more failed sign-ins in a short period than the threshold allows
- **THEN** further attempts against it are refused for a period, and the refusal says when it may be tried again

#### Scenario: The right password during a lockout

- **WHEN** a correct password is offered while an account is locked out
- **THEN** it is still refused, because otherwise the lockout only delays a guess that has already succeeded

#### Scenario: The application restarts mid-attack

- **WHEN** the application restarts while an account is locked out
- **THEN** the lockout still stands, having been recorded where a restart does not reach

#### Scenario: A lockout does not reveal an account

- **WHEN** a locked-out account and an account that does not exist are both attempted
- **THEN** the two refusals are indistinguishable

#### Scenario: A successful sign-in clears the run

- **WHEN** a person signs in correctly before reaching the threshold
- **THEN** the failures recorded against that account no longer count toward a lockout

#### Scenario: One person's mistakes do not lock out another

- **WHEN** one account is locked out
- **THEN** every other account signs in unaffected
