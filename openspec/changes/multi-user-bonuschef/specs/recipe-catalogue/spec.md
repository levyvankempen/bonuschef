# recipe-catalogue

## ADDED Requirements

### Requirement: The catalogue is shared and what is written about a recipe is personal

A recipe in the catalogue SHALL be visible to every account. Anything recorded
*about* a recipe by an account - whether it is saved, its edits, its notes,
when it was last made - SHALL belong to that account alone.

The reason to share the catalogue is that adding a recipe is work and the
result is the same for everyone. The reason not to share the annotations is
that they are opinions: one person halving the garlic should not change what
anybody else cooks.

#### Scenario: A person adds a recipe

- **WHEN** a person adds a recipe, their own or one from the retailer
- **THEN** it becomes available to every account, and is saved to that person's collection

#### Scenario: A person edits a shared recipe

- **WHEN** a person changes ingredients or quantities on a recipe others can also see
- **THEN** their version is what they see from then on, and every other account still sees the original

#### Scenario: Two people save the same recipe

- **WHEN** two accounts save the same catalogue recipe
- **THEN** each has it in their own collection with their own edits, notes and last-made date

### Requirement: A person records when they last made a recipe

An account SHALL be able to record that it made a recipe, and the date of the
most recent time SHALL be shown wherever that account's recipes are listed.

This is the field that makes a collection useful rather than merely long: the
question being asked of it is usually "what have I not had for a while".

#### Scenario: A recipe has been made

- **WHEN** a person marks a recipe as made
- **THEN** the date is recorded against their account and shown on that recipe

#### Scenario: A recipe has never been made

- **WHEN** a person's saved recipe has no recorded date
- **THEN** that is shown as not yet made, rather than as an empty or zero date

### Requirement: How an ingredient resolves to a product is shared, not personal

The link between an ingredient identity and the products that satisfy it
SHALL be a property of the catalogue, visible to and usable by every account.

This is the line between a fact and an opinion. That "sjalot" is satisfied by
AH Sjalotten is true for everybody; that a recipe should use half the garlic
is not. There are roughly 1,900 such resolutions and each cost a search
against the retailer. Scoping them per account would hand every new person an
unpriceable catalogue and ask them to redo work already done.

It also preserves the existing requirements that a correction applies to every
recipe using that ingredient, which would otherwise be contradicted.

#### Scenario: A person corrects a match

- **WHEN** a person corrects which product satisfies an ingredient
- **THEN** the correction applies to every recipe using that ingredient, for every account

#### Scenario: A new account opens a recipe

- **WHEN** an account that has resolved nothing itself opens a recipe
- **THEN** it is priced from the catalogue's existing resolutions

#### Scenario: A person changes a quantity

- **WHEN** a person changes how much of an ingredient their copy of a recipe uses
- **THEN** only their copy changes, because a quantity is theirs while a resolution is the catalogue's

## MODIFIED Requirements

### Requirement: A recipe can be adopted from the retailer's catalogue

A person SHALL be able to add a recipe by finding it in the retailer's own catalogue rather than by entering it. An adopted recipe SHALL carry its title, its serving count, and each ingredient with the quantity the recipe calls for. An adopted recipe SHALL enter the shared catalogue and SHALL be saved to the collection of the account that adopted it.

#### Scenario: Finding a recipe by name

- **WHEN** a person searches the catalogue for a dish
- **THEN** matching recipes are offered, identified well enough to choose between them

#### Scenario: Adopting a recipe

- **WHEN** a person adopts a recipe from the results
- **THEN** it becomes one of their recipes, with its ingredients and quantities, without further typing

#### Scenario: The same recipe twice

- **WHEN** a person adopts a recipe they already have
- **THEN** they are not given a duplicate

#### Scenario: A recipe another account already adopted

- **WHEN** a person adopts a recipe that is already in the shared catalogue because someone else added it
- **THEN** it is not duplicated, and it appears in this person's collection with their own edits, notes and last-made date

#### Scenario: A hand-entered recipe

- **WHEN** a person enters a recipe of their own rather than adopting one
- **THEN** it is treated the same way everywhere downstream; adoption is an additional path, not a replacement
