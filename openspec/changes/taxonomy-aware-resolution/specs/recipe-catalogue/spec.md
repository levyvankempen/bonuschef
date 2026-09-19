## ADDED Requirements

### Requirement: A product carries what kind of thing it is

A product SHALL carry the retailer's own classification of it — its taxonomy
path and the department of the store it is sold from — alongside its name and
price.

A name says what a product is called. A classification says what it is. The
two are not the same, and resolution has until now had only the first.

#### Scenario: Classification is available wherever a product is

- **WHEN** a product is considered as a candidate for an ingredient
- **THEN** what kind of thing it is can be read, without a further request to the retailer

#### Scenario: The retailer does not classify a product

- **WHEN** a product carries no classification
- **THEN** it is still usable, and the checks that depend on classification abstain rather than rejecting it

### Requirement: A candidate whose kind contradicts the ingredient is not proposed

A product SHALL NOT be proposed for an ingredient when its classification
contradicts what the ingredient is.

A food ingredient SHALL NOT be resolved by a non-food product. An ingredient
that asks for something fresh SHALL NOT be resolved by a product the retailer
sells as ambient or dried, and the reverse SHALL also hold.

These are not close calls. A live audit found a paper napkin resolving
"wortel", cough syrup resolving "kropje babyromainesla", and menstrual
painkillers resolving "runderbouillon van tablet" — each arrived at by a
confident name match.

#### Scenario: A non-food product matches the name

- **WHEN** a product outside the food departments carries the ingredient's name in its title
- **THEN** it is not proposed, because an ingredient cannot be satisfied by something inedible

#### Scenario: An ingredient asks for fresh

- **WHEN** an ingredient names a fresh form and a candidate is sold as a dried or ambient product
- **THEN** that candidate is not proposed, so "verse dille" is not satisfied by dried dill in a jar

#### Scenario: The ingredient says nothing about form

- **WHEN** an ingredient does not state a form
- **THEN** no candidate is rejected on that basis, because silence is not a requirement

### Requirement: A candidate the taxonomy names is preferred to one that merely mentions it

Where a candidate's classification names the ingredient, it SHALL be preferred
to a candidate whose title merely contains the ingredient's name.

A product classified as "Witte kaas" is white cheese. A product whose title
contains "witte kaas" may be a cheeseboard accompaniment, a dressing, or a
salami.

#### Scenario: The taxonomy names the ingredient

- **WHEN** one candidate is classified under the ingredient's own name and another only mentions it
- **THEN** the classified one is proposed ahead of the other

#### Scenario: Nothing is classified under the ingredient

- **WHEN** no candidate's classification names the ingredient
- **THEN** the existing ordering decides, so this preference adds an answer and never removes one

### Requirement: Resolutions already recorded are re-checked

Resolutions already in the system SHALL be checked against classification when
it becomes available, and those that contradict it SHALL be surfaced for
review.

A check applied only to new proposals leaves every wrong answer already
recorded in place, which is where the known wrong answers actually are.

#### Scenario: An existing resolution contradicts its classification

- **WHEN** a recorded resolution is found to contradict what its product is
- **THEN** it is raised for review rather than silently kept or silently deleted

#### Scenario: A person has already decided

- **WHEN** a recorded resolution was confirmed by a person
- **THEN** it is left alone, because a human decision outranks a classification rule

### Requirement: A person reviewing a match can see what each candidate is

When a person is choosing between candidate products for an ingredient, each
candidate SHALL show what kind of thing it is.

#### Scenario: Choosing between similarly named products

- **WHEN** several candidates carry similar names
- **THEN** what distinguishes them is visible without opening the retailer's website
