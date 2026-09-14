## ADDED Requirements

### Requirement: A person can correct how an ingredient resolves

A person SHALL be able to change which products satisfy an ingredient, and their decision SHALL persist. An automatic proposal SHALL NOT overwrite a decision a person has made, however many times the matcher runs afterwards.

#### Scenario: Correcting a wrong proposal

- **WHEN** a person replaces the products proposed for an ingredient
- **THEN** the replacement is what every recipe using that ingredient costs against

#### Scenario: The matcher runs again

- **WHEN** the automatic matcher runs over an ingredient a person has already decided
- **THEN** the person's decision stands, and the matcher does not silently revert it

#### Scenario: Filling a gap the matcher left

- **WHEN** the matcher runs over an ingredient nobody has decided
- **THEN** it may add products, because an untouched proposal is not a decision

#### Scenario: A decision is distinguishable from a guess

- **WHEN** a resolution is inspected
- **THEN** whether a person chose it or the matcher proposed it is apparent

### Requirement: An ingredient with no purchasable equivalent can be recorded as such

A person SHALL be able to record that nothing in the catalogue satisfies an ingredient. That state SHALL be distinguishable from an ingredient nobody has examined yet, and SHALL NOT be undone by the matcher.

#### Scenario: Nothing satisfies it

- **WHEN** a person concludes that no product corresponds to an ingredient
- **THEN** that conclusion is recorded, and the ingredient stops appearing as outstanding work

#### Scenario: Still unexamined

- **WHEN** an ingredient has never been reviewed
- **THEN** it is distinguishable from one a person has examined and found nothing for

#### Scenario: The cost stays honest either way

- **WHEN** a recipe contains an ingredient with no purchasable equivalent
- **THEN** its cost is still reported as incomplete, because an ingredient that cannot be bought is not an ingredient that is free

### Requirement: A recipe costs the cheapest product that satisfies each ingredient

Where several products satisfy an ingredient, the cost SHALL use the cheapest one whose price is known. Products whose price is unknown SHALL NOT be treated as cheaper than those whose price is known.

#### Scenario: Several products, different prices

- **WHEN** an ingredient resolves to more than one product
- **THEN** the recipe costs the cheapest of them

#### Scenario: One of them has no known price

- **WHEN** some of the products satisfying an ingredient have no observed price
- **THEN** the cheapest priced one is used, rather than the unpriced one being taken as free

#### Scenario: None of them has a known price

- **WHEN** no product satisfying an ingredient has an observed price
- **THEN** the ingredient counts as unpriced and the recipe's total is withheld
