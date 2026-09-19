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

### Requirement: Only candidates of the same kind as the best one are proposed

Where several products are proposed for one ingredient, they SHALL all be the
same kind of thing as the best of them.

Proposing everything a search returns is not harmless. The cheapest candidate
decides a recipe's cost, so a single wrong candidate can decide it — a cream
cheese among the shallots sets the price of a dish containing no cream cheese.

#### Scenario: One candidate is a different kind of thing

- **WHEN** a search returns products of which some are the ingredient and some merely mention it
- **THEN** only those of the same kind as the best match are proposed

#### Scenario: Several genuinely interchangeable products

- **WHEN** several proposed products are the same kind of thing
- **THEN** all of them are kept, because which is cheapest changes from day to day and that is the point

#### Scenario: The best candidate is unclassified

- **WHEN** the best candidate carries no classification to compare against
- **THEN** nothing is narrowed, because there is no evidence on which to narrow it

### Requirement: Resolutions already recorded are re-checked

Resolutions already in the system SHALL be checked against classification when
it becomes available, and those that contradict it SHALL be surfaced for
review.

A check applied only to new proposals leaves every wrong answer already
recorded in place, which is where the known wrong answers actually are.

#### Scenario: An existing resolution contradicts its classification

- **WHEN** a recorded resolution is found to contradict what its product is
- **THEN** it is raised for review rather than silently kept or silently deleted

#### Scenario: A concept a person already settled is found to be wrong

- **WHEN** a concept that was reviewed is later found to contradict itself
- **THEN** it returns to the queue of things to look at, ahead of ingredients that were never linked at all

#### Scenario: A wrong link is described differently from a missing one

- **WHEN** an ingredient is linked to a product that contradicts it
- **THEN** it is presented as a price that is wrong rather than as a gap, because the recipe already shows a cost and nothing otherwise looks amiss

#### Scenario: Everything is linked but some links are wrong

- **WHEN** no ingredient is unlinked but some links contradict themselves
- **THEN** the way to review them is still offered

#### Scenario: A flagged concept is settled

- **WHEN** a person confirms a resolution for a flagged concept
- **THEN** it stops being flagged, rather than returning to the head of the queue they just cleared it from

#### Scenario: A person has already decided

- **WHEN** a recorded resolution was confirmed by a person
- **THEN** it is left alone, because a human decision outranks a classification rule

#### Scenario: The only recorded product is a non-food one

- **WHEN** an ingredient's only recorded product is one it can never be satisfied by
- **THEN** that resolution is withdrawn even though nothing replaces it, because an ingredient with no product is already shown as unresolved, while a wrong one is silently priced

#### Scenario: The only recorded product is merely the wrong form

- **WHEN** an ingredient's only recorded product is edible but in a form the ingredient did not ask for
- **THEN** it is kept and raised for review, because a worse match is not an impossible one

### Requirement: A person reviewing a match can see what each candidate is

When a person is choosing between candidate products for an ingredient, each
candidate SHALL show what kind of thing it is.

#### Scenario: Choosing between similarly named products

- **WHEN** several candidates carry similar names
- **THEN** what distinguishes them is visible without opening the retailer's website

### Requirement: An ingredient is searched for by what it is, not how it is sold

Where an ingredient names the container it comes in, the search for products
SHALL also be made without it.

The container word is matched by the retailer's own search, which then returns
the packaging rather than the food: "cannellinibonen in blik" returns tuna,
corn and pineapple, and "runderbouillon van tablet" returns Ibuprofen and
Paracetamol, both sold as tabletten. Removing the container returns the bean
and the stock.

#### Scenario: An ingredient names its container

- **WHEN** an ingredient names the container it is sold in
- **THEN** products are also sought for the ingredient without it, and the results of both are considered

#### Scenario: A qualifier that is not a container

- **WHEN** an ingredient names what it is packed in rather than what it is packed as
- **THEN** it is kept, because tuna in oil and tuna in water are different products and a recipe asking for one means it

### Requirement: The retailer's own label is preferred between equivalent products

Where two products satisfy an ingredient equally, the retailer's own label
SHALL be preferred, unless the recipe named a brand.

#### Scenario: Two products of the same kind

- **WHEN** an own-label product and another brand are both the right kind of thing
- **THEN** the own label is preferred, being usually the cheaper of the two

#### Scenario: An own-label product of the wrong kind

- **WHEN** an own-label product is not the kind of thing the ingredient asks for
- **THEN** it is not preferred over a correctly matched product from another brand

#### Scenario: The recipe named a brand

- **WHEN** an ingredient names a particular brand
- **THEN** that is honoured rather than overridden by the own label
