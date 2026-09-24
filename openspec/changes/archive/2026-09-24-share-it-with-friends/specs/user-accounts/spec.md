## ADDED Requirements

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

## MODIFIED Requirements

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
