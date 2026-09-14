## Purpose

Defines what makes a recipe worth cooking today: how a saving is established against what a recipe ordinarily costs, which recipes are eligible to be considered at all, and what must be withheld when the evidence is incomplete, stale, or about something the shop will have sold by the time anyone gets there.

## ADDED Requirements

### Requirement: A recipe's saving is measured against what it ordinarily costs

A saving SHALL be the difference between a recipe's ordinary cost and its cost using the discounts available now. The ordinary cost SHALL be the price the system itself has observed, not a price the retailer advertises as the former one.

#### Scenario: An ingredient is discounted

- **WHEN** an ingredient of a recipe is available below the price the system ordinarily observes for it
- **THEN** the recipe's saving includes that difference

#### Scenario: The retailer's claim differs from the observed price

- **WHEN** a retailer advertises a larger saving than the observed price supports
- **THEN** the ranking uses the observed figure, and the advertised one may be shown alongside it but never in its place

#### Scenario: Nothing is discounted

- **WHEN** none of a recipe's ingredients is discounted
- **THEN** its saving is nought, and it is not presented as an opportunity

#### Scenario: Two discounts on one ingredient

- **WHEN** an ingredient is both on clearance and on promotion
- **THEN** the cheaper of the two is what counts, and which one it was is apparent

### Requirement: Only recipes that can be honestly costed are ranked

A recipe SHALL be eligible for ranking only when every one of its ingredients resolves to a product with a known price. A recipe with an unresolved or unpriced ingredient SHALL NOT be ranked, because its total is unknown and an unknown total cannot be compared.

#### Scenario: A recipe with an unresolved ingredient

- **WHEN** a recipe contains an ingredient that resolves to no product
- **THEN** it does not appear in the ranking, and the reason is discoverable rather than silent

#### Scenario: A recipe becomes eligible

- **WHEN** the last unresolved ingredient of a recipe is resolved
- **THEN** the recipe becomes eligible without any other action

#### Scenario: An incomplete recipe is not simply hidden

- **WHEN** recipes are excluded for being incompletely costed
- **THEN** that they exist and why they were excluded is available, so the ranking is not quietly narrower than it appears

### Requirement: A saving rests on a comparable reference price

A saving SHALL NOT be claimed where the ordinary price it is measured against was observed too long ago to describe the present market. Such an ingredient SHALL be treated as not discounted rather than as discounted by an unknown amount.

#### Scenario: The reference price is recent

- **WHEN** the ordinary price of a discounted ingredient was observed recently
- **THEN** the saving is counted

#### Scenario: The reference price predates the season

- **WHEN** the only observed price for an ingredient is many months old
- **THEN** no saving is counted for that ingredient, and the recipe is ranked on its remaining ingredients

### Requirement: Clearance urgency reaches the answer

Where a recipe's saving depends on a clearance item, the ranking SHALL carry what makes that item urgent — how little is left and when it expires — because those decide whether the plan survives the journey to the shop.

#### Scenario: Very little stock remains

- **WHEN** a recipe's saving depends on an item with very few left
- **THEN** that is shown with the recipe, not discovered on arrival at the shop

#### Scenario: The item expires today

- **WHEN** a clearance item must be eaten today
- **THEN** that is shown, because it argues for cooking the recipe tonight rather than later

#### Scenario: An opportunity that has already gone

- **WHEN** the clearance snapshot the ranking rests on is no longer from the current trading day
- **THEN** no clearance-based opportunity is presented as available now

### Requirement: Clearance prices do not enter the comparable cost history

A recipe's recorded cost over time SHALL NOT include store-specific clearance pricing. Clearance is scoped to one shop, lasts hours, and is limited by stock, so including it would make a recipe appear to have become cheaper when only one shop briefly discounted one item.

#### Scenario: A recipe's cost over time

- **WHEN** a recipe's cost is recorded for comparison across days
- **THEN** it reflects ordinary and promotional pricing, not clearance

#### Scenario: Today's opportunity

- **WHEN** today's opportunity is computed
- **THEN** clearance is included, because that is what makes it an opportunity

### Requirement: The pool of recipes considered is bounded and stated

The system SHALL consider a bounded set of recipes, and SHALL be able to widen it over time within a stated limit on requests to the retailer. It SHALL NOT attempt to hold the retailer's entire catalogue, and SHALL NOT make the size of the pool invisible to the person relying on it.

#### Scenario: A person has adopted few recipes

- **WHEN** someone has adopted only a handful of recipes
- **THEN** the ranking still draws on more than those, so the answer is useful before a large collection exists

#### Scenario: The cost of widening is bounded

- **WHEN** the pool is widened
- **THEN** the number of requests made to the retailer is limited and paced, so that interactive use and the scheduled collection are not degraded

#### Scenario: The pool is not presented as the whole catalogue

- **WHEN** a ranking is shown
- **THEN** it is apparent that it covers a pool of recipes rather than everything the retailer publishes
