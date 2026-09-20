# recipe-catalogue

## ADDED Requirements

### Requirement: A candidate that is not recognisably the ingredient is not proposed

Where the best candidate for an ingredient is not recognisable as that
ingredient, no candidate SHALL be proposed and the ingredient SHALL be shown
as unresolved.

A candidate is recognisable when its classification names the ingredient, or
when the head nouns of the ingredient and the product agree. Either alone
suffices.

Ranking always produces a winner, even when every candidate is wrong. "Blauwe
kaas-blokjes" was priced as AH Blauwe bessen and "salade-uitjes" as AH Ei
salade: both food, both fresh, both sharing a word with the ingredient, so
every rule about kind and form accepted them. A cost built on those is worse
than no cost, because it looks right.

The test is deliberately about naming rather than degree of confidence. A
numeric floor was measured against the human-confirmed links and did not
separate: confirmed products scored as low as -1.20 while correct matches that
happened not to be confirmed scored 10.00, so every cut that removed a wrong
answer removed good ones too.

#### Scenario: The best candidate shares a word but is a different product

- **WHEN** the best candidate is neither named by its classification nor in head-noun agreement with the ingredient
- **THEN** nothing is proposed, and the ingredient is shown as unresolved rather than priced

#### Scenario: Only the product's name identifies it

- **WHEN** a candidate's classification is broader than the ingredient but its name agrees
- **THEN** it is proposed, because either evidence suffices

#### Scenario: The ingredient is written as a diminutive

- **WHEN** a recipe names an ingredient in a diminutive form and the product carries the plain noun
- **THEN** they are recognised as the same thing, because recipes routinely use diminutives the shelf label does not

#### Scenario: The ingredient is a compound of the product's general term

- **WHEN** an ingredient's name ends in the word its candidate is named by, or the reverse
- **THEN** they are recognised as the same thing, because a compound names its head last

#### Scenario: A person already confirmed the pairing

- **WHEN** a recorded resolution was confirmed by a person
- **THEN** it stands regardless of whether any rule can recognise it, because some correct pairings share no word at all

## MODIFIED Requirements

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

- **WHEN** the best candidate carries no classification to compare against, but is recognisable as the ingredient by name
- **THEN** nothing is narrowed, because there is no evidence on which to narrow it

#### Scenario: The best candidate is unclassified and unrecognisable

- **WHEN** the best candidate carries no classification and is not recognisable as the ingredient by name either
- **THEN** nothing is proposed at all, because narrowing and withholding are different decisions and only the second one applies

### Requirement: Resolutions already recorded are re-checked

Resolutions already in the system SHALL be checked against classification when
it becomes available, and those that contradict it SHALL be surfaced for
review. The check SHALL apply the same recognisability test as a new proposal.

A check applied only to new proposals leaves every wrong answer already
recorded in place, which is where the known wrong answers actually are. A
check that examines only form and department leaves the ones that agree on
both: AH Blauwe bessen and "blauwe kaas-blokjes" are both food and both fresh.

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

#### Scenario: The only recorded product is not the ingredient at all

- **WHEN** an ingredient's only recorded product is edible and of the right form, but is not recognisable as the ingredient
- **THEN** that resolution is withdrawn even though nothing replaces it, and the concept is flagged, because this is the wrong product rather than a worse one

#### Scenario: A recorded product cannot be classified

- **WHEN** a recorded product is one the retailer no longer classifies
- **THEN** it is left alone, because unknown is not wrong
