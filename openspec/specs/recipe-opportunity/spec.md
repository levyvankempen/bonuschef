# recipe-opportunity Specification

## Purpose

Defines what makes a recipe worth cooking today: how a saving is established against what a recipe ordinarily costs, what may be claimed when the evidence is partial, and what must be withheld when it is stale, conditional, or about something the shop will have sold by the time anyone gets there.

## Requirements

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

#### Scenario: The discount is on a different product than usual

- **WHEN** an ingredient resolves to several products and the cheapest today is not the one ordinarily bought
- **THEN** the saving is measured against the ordinary choice, and it is never negative

### Requirement: A saving may rest on partial knowledge; a total may not

A recipe SHALL be eligible for ranking when at least one of its ingredients is discounted against a comparable reference price, even if other ingredients resolve to no product or to no known price. An unpriced ingredient makes a recipe's **total** unknown; it does not make the **saving** unknown, because an ingredient that contributes nothing to the saving cannot change it.

A saving computed over an incompletely priced recipe SHALL be presented as a lower bound and never as an exact figure.

The cost of such a recipe MAY be presented as an estimate, marked as one and accompanied by how many ingredients it covers. This is a deliberate departure from the comparable cost history, which withholds a total entirely: a series has to be comparable with itself, while a person choosing what to cook is better served by a rough figure they can correct than by no figure at all. The two SHALL NOT be conflated, and the recorded cost history SHALL continue to withhold.

#### Scenario: A recipe with one unresolved ingredient is still ranked

- **WHEN** a recipe has a discounted ingredient and also an ingredient that resolves to no product
- **THEN** it is ranked on the saving that is known, and that saving is shown as a lower bound

#### Scenario: An estimate is never mistaken for a total

- **WHEN** a ranked recipe is not fully priced
- **THEN** any cost shown for it is marked as an estimate and carries the number of ingredients it rests on

#### Scenario: The recorded history still withholds

- **WHEN** a recipe's cost is recorded for comparison across days
- **THEN** nothing is recorded for an incompletely priced recipe, because a series must be comparable with itself

#### Scenario: A recipe with nothing priced

- **WHEN** none of a recipe's ingredients resolves to a product with a known price
- **THEN** it cannot be ranked, because there is no evidence either way

#### Scenario: Recipes are never silently dropped

- **WHEN** recipes are not ranked, for any reason
- **THEN** that they exist and why each was not ranked remains available, so the ranking is not quietly narrower than it appears

#### Scenario: Resolving an ingredient improves the answer without any other action

- **WHEN** an unresolved ingredient of a recipe is resolved to a product
- **THEN** the recipe's known saving and its coverage improve on the next rebuild, with nothing else to do

### Requirement: A saving rests on a comparable reference price

A saving SHALL NOT be claimed where the ordinary price it is measured against was observed too long ago to describe the present market. Such an ingredient SHALL be treated as not discounted rather than as discounted by an unknown amount.

#### Scenario: The reference price is recent

- **WHEN** the ordinary price of a discounted ingredient was observed recently
- **THEN** the saving is counted

#### Scenario: The reference price predates the season

- **WHEN** the only observed price for an ingredient is many months old
- **THEN** no saving is counted for that ingredient, and the recipe is ranked on its remaining ingredients

#### Scenario: An offer that had to be ignored is not invisible

- **WHEN** a discount is discarded because its reference price is too old
- **THEN** that this happened is recorded, so "why is this not cheaper" has an answer

### Requirement: A saving conditional on buying more than the recipe needs is not a saving

Where a promotion's per-unit price is obtainable only by buying more units than the recipe calls for, that price SHALL NOT be counted in the recipe's saving. Such an offer MAY be reported separately as conditional, and its condition SHALL be stated.

#### Scenario: A multibuy promotion on an ingredient needed once

- **WHEN** an ingredient is on a promotion whose price requires buying two, and the recipe needs one
- **THEN** the recipe's saving does not include it

#### Scenario: The conditional offer is still worth knowing about

- **WHEN** a recipe has an ingredient on such a promotion
- **THEN** it may be shown alongside the saving, described as requiring the larger purchase, and never added into the ranked figure

### Requirement: A saving on part of a pack is described as what it is

Where a recipe uses less than a whole unit of a product, the cost and the saving SHALL be those of the whole unit, because that is what has to be bought. This SHALL be apparent wherever a saving is shown, so that a discount on a large pack used sparingly is not read as money saved on the meal.

#### Scenario: A recipe uses part of a pack

- **WHEN** a recipe calls for less than the whole of a discounted product
- **THEN** the figure shown is the whole unit's, and that it covers the whole unit is stated

### Requirement: Clearance urgency reaches the answer

Where a recipe's saving depends on a clearance item, the ranking SHALL carry what makes that item urgent — how little is left and when it expires — because those decide whether the plan survives the journey to the shop.

#### Scenario: Very little stock remains

- **WHEN** a recipe's saving depends on an item with very few left
- **THEN** that is shown with the recipe, not discovered on arrival at the shop

#### Scenario: The item expires today

- **WHEN** a clearance item must be eaten today
- **THEN** that is shown, because it argues for cooking the recipe tonight rather than later

#### Scenario: How much is left is not known

- **WHEN** the remaining stock of a clearance item a recipe depends on is unknown
- **THEN** no bound on it is stated, rather than an unknown being shown as plenty

#### Scenario: One item claimed by two ingredients

- **WHEN** two ingredients of a recipe resolve to the same clearance item and too few remain for both
- **THEN** the saving does not count that item twice unnoticed

### Requirement: Clearance evidence is withdrawn rather than the answer being blanked

WHEN the clearance snapshot is no longer from the current trading day, the ranking SHALL cease to rest on clearance and SHALL be recomputed on promotional pricing alone, which is neither store-specific nor perishable within the day. The withdrawal SHALL be stated. The ranking SHALL NOT be blanked merely because one of its two sources of evidence has aged out.

#### Scenario: Yesterday's clearance, today's promotions

- **WHEN** the clearance snapshot is from a previous trading day and promotions are current
- **THEN** recipes are re-ranked on promotions alone, clearance prices are not shown as available, and that clearance has been set aside is said

#### Scenario: The judgement is made when the page is read

- **WHEN** a ranking built yesterday is read today
- **THEN** whether clearance still counts is decided from the snapshot's age at the moment of reading, not at the moment the ranking was built

### Requirement: Clearance prices do not enter the comparable cost history

A recipe's recorded cost over time SHALL NOT include store-specific clearance pricing. Clearance is scoped to one shop, lasts hours, and is limited by stock, so including it would make a recipe appear to have become cheaper when only one shop briefly discounted one item.

#### Scenario: A recipe's cost over time

- **WHEN** a recipe's cost is recorded for comparison across days
- **THEN** it reflects ordinary and promotional pricing, not clearance

#### Scenario: Today's opportunity

- **WHEN** today's opportunity is computed
- **THEN** clearance is included, because that is what makes it an opportunity

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

### Requirement: A person's own recipes outrank the pool and are never evicted

A recipe a person has adopted or entered SHALL NOT be removed by a pool refresh, regardless of its rating or whether it still appears in the retailer's popular listing.

#### Scenario: An adopted recipe falls out of the popular listing

- **WHEN** the pool is refreshed and an adopted recipe is no longer among the well-rated
- **THEN** it is kept, because the person chose it and that outranks the retailer's ordering

### Requirement: A person can dismiss a recipe and stop seeing it

A person SHALL be able to reject a recipe from the pool, and a rejected recipe SHALL NOT be recommended again. The rejection SHALL survive a pool refresh, so that dismissing something is permanent until the person reverses it.

A person SHALL also be able to keep a recipe, which adopts it into their own and exempts it from eviction.

#### Scenario: Rejecting a recommendation

- **WHEN** a person rejects a recipe they do not want to cook
- **THEN** it does not appear in any later ranking

#### Scenario: A rejection outlives the pool it was made against

- **WHEN** the pool is refreshed and a rejected recipe is fetched again
- **THEN** it remains rejected without the person having to reject it twice

#### Scenario: Keeping a recipe that keeps coming up

- **WHEN** a person keeps a recipe that has been recommended to them
- **THEN** it becomes one of their own and is never evicted by a refresh

#### Scenario: Changing one's mind

- **WHEN** a person looks at what they have rejected
- **THEN** they can reverse any of it, so a dismissal is not a trap

#### Scenario: Dismissals are not silently lost

- **WHEN** a recipe is rejected
- **THEN** it remains listed as rejected rather than vanishing without record

#### Scenario: The budget is exhausted or the credential is rejected

- **WHEN** maintaining the pool would exceed the daily budget, or the retailer rejects the credential
- **THEN** pool maintenance stops and stays stopped until a person intervenes, while clearance collection and the credential heartbeat continue unaffected

#### Scenario: Pool maintenance never delays clearance

- **WHEN** pool maintenance is scheduled
- **THEN** it runs outside the hours clearance is collected, and cannot occupy the warehouse while a clearance scrape is due

#### Scenario: The pool is not presented as the whole catalogue

- **WHEN** a ranking is shown
- **THEN** how many recipes are held and how many of them can presently be ranked are both apparent, because the gap between them is the honest state of the system
