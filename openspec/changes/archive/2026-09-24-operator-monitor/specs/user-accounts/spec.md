## MODIFIED Requirements

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
