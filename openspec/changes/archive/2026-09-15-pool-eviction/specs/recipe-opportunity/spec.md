## MODIFIED Requirements

### Requirement: The pool is the well-regarded recipes, not the whole catalogue

The system SHALL hold a bounded pool of recipes chosen by how well the retailer's own readers rate them, rather than the entire published catalogue. The bound SHALL be a stated number of recipes, and the pool SHALL be refreshed rather than accumulated, so that it does not grow without limit.

A refresh SHALL leave the pool holding what that refresh found. A recipe absent from the latest enumeration SHALL NOT remain in the pool merely because an earlier one included it.

A recipe's rating and the number of votes behind it SHALL be held with it, because a five-star average over three votes is not the same claim as one over three hundred.

#### Scenario: The pool is refreshed, not accumulated

- **WHEN** the pool is rebuilt
- **THEN** recipes that have fallen out of favour leave it, and the total held stays within the stated bound

#### Scenario: A recipe drops out of the retailer's listing

- **WHEN** a refresh returns a listing that no longer contains a recipe the pool held
- **THEN** that recipe is gone from the pool, rather than surviving because nothing removed it

#### Scenario: A thinly voted recipe

- **WHEN** a recipe's rating rests on very few votes
- **THEN** how many votes it rests on is available wherever the rating is shown

#### Scenario: A person has adopted few recipes

- **WHEN** someone has adopted only a handful of recipes
- **THEN** the ranking still draws on the pool, so the answer is useful before a large collection exists
