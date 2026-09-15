# price-intelligence Specification

## Purpose

Defines what the warehouse is entitled to assert about prices, savings and promotions: when a comparison between two prices is meaningful, when a promotion counts as live, and what must be withheld rather than estimated — so that the project's central claim, that advertised supermarket savings are often overstated, rests on evidence rather than on stale rows.

## Requirements

### Requirement: A promotion is reported as live only while it is running

Promotional pricing SHALL be reported as current only when the promotion's period includes the present date. A promotion that has ended SHALL NOT be presented as an offer. A sentinel far-future end date SHALL be distinguishable from a dated campaign, because the two are different propositions and a consumer must be able to tell them apart — but it SHALL NOT be excluded, because such offers are real standing shelf discounts.

#### Scenario: A promotion that ended weeks ago

- **WHEN** a promotion's end date is in the past
- **THEN** the affected product is not reported as on offer

#### Scenario: A promotion running today

- **WHEN** the present date falls within a promotion's start and end dates
- **THEN** the product is reported as on offer, with its promotional price

#### Scenario: A far-future sentinel end date

- **WHEN** a promotion carries an end date so distant that it cannot be a dated campaign
- **THEN** it is still reported as on offer, because it is a standing discount rather than a stale row, and it is marked as ongoing so that it is never mistaken for a campaign ending this week

#### Scenario: The promotional feed has stopped loading

- **WHEN** the source of promotions has not loaded recently enough to describe today
- **THEN** no product is reported as on offer on the strength of that stale feed

### Requirement: A saving is only claimed against a comparable price

A saving SHALL be computed only where the reference price was observed recently enough to describe the same market conditions. Where the reference price is too old to be comparable, the saving SHALL be reported as unknown rather than computed.

#### Scenario: The reference price is recent

- **WHEN** a product's observed reference price is recent
- **THEN** the saving against the current price is computed and reported

#### Scenario: The reference price predates the current season

- **WHEN** the most recent observation of a product's price is many months old, because the product left the catalogue
- **THEN** no saving is reported for it, rather than a saving measured against a price from a different year

#### Scenario: The age of a reference price is inspectable

- **WHEN** a consumer reads a product's reference price
- **THEN** it can also read when that price was observed, without inferring it

### Requirement: An advertised saving and an observed saving are distinguishable

Where a retailer advertises a saving, the warehouse SHALL report both that advertised figure and the saving measured against the price the system itself observed, as separate values. Neither SHALL be substituted for the other.

#### Scenario: The advertised saving exceeds the observed saving

- **WHEN** a retailer's stated "before" price is higher than the price the system last observed
- **THEN** both figures are available, and the discrepancy is derivable

#### Scenario: No observed price exists

- **WHEN** the system has never observed a product's price independently
- **THEN** the advertised saving is still reported, and the observed saving is reported as unknown rather than as zero

### Requirement: Products are identified by a stable key across sources

Products arriving from different sources SHALL be reconciled through a single shared mapping. Where a product has been known by more than one identifier over time, the mapping SHALL resolve to the most recently observed one.

#### Scenario: A product has been renamed

- **WHEN** a product has appeared under more than one identifier across the catalogue's history
- **THEN** the mapping resolves it to the identifier from the most recent observation, not an arbitrary one

#### Scenario: The same reconciliation is used everywhere

- **WHEN** two different consumers reconcile the same product between sources
- **THEN** they obtain the same result, because the reconciliation is defined in one place

#### Scenario: A product cannot be reconciled

- **WHEN** an item from one source has no counterpart in the catalogue
- **THEN** it is still reported, with its reconciliation-dependent measures marked unknown rather than dropped
