## Purpose

Defines how a recipe enters the system without being typed, and how its ingredients acquire an identity that can be priced — so that going from two recipes to twenty costs minutes rather than an evening, and so that an ingredient nobody can price is visibly unpriced rather than quietly absent.

## ADDED Requirements

### Requirement: A recipe can be adopted from the retailer's catalogue

A person SHALL be able to add a recipe by finding it in the retailer's own catalogue rather than by entering it. An adopted recipe SHALL carry its title, its serving count, and each ingredient with the quantity the recipe calls for.

#### Scenario: Finding a recipe by name

- **WHEN** a person searches the catalogue for a dish
- **THEN** matching recipes are offered, identified well enough to choose between them

#### Scenario: Adopting a recipe

- **WHEN** a person adopts a recipe from the results
- **THEN** it becomes one of their recipes, with its ingredients and quantities, without further typing

#### Scenario: The same recipe twice

- **WHEN** a person adopts a recipe they already have
- **THEN** they are not given a duplicate

#### Scenario: A hand-entered recipe

- **WHEN** a person enters a recipe of their own rather than adopting one
- **THEN** it is treated the same way everywhere downstream; adoption is an additional path, not a replacement

### Requirement: Ingredients carry a reusable identity

An ingredient SHALL be recorded against the retailer's stable identity for that ingredient, not only as text. Where two recipes call for the same ingredient, they SHALL share that identity, so effort spent resolving it is spent once.

#### Scenario: An ingredient shared between recipes

- **WHEN** two adopted recipes each call for the same ingredient
- **THEN** both reference the same ingredient identity, and resolving it once serves both

#### Scenario: A variant is a distinct ingredient

- **WHEN** the catalogue distinguishes a variant of an ingredient from its ordinary form
- **THEN** that distinction is preserved rather than collapsed, because the two have different prices and availability

#### Scenario: The retailer's text still travels with it

- **WHEN** an ingredient is recorded
- **THEN** its human-readable name is kept alongside the identity, so a person can read a recipe without a lookup

### Requirement: An ingredient is resolved to purchasable products explicitly

An ingredient identity SHALL be resolved to the products that satisfy it. The system SHALL propose candidates automatically, and a proposal SHALL persist and be reused by every recipe sharing that ingredient. Proposing SHALL NOT interrupt adoption: a person who adopts twenty recipes SHALL not be asked twenty times.

#### Scenario: A confident candidate

- **WHEN** the system finds a product that clearly satisfies an ingredient
- **THEN** it is proposed as the resolution, and accepting it requires no work

#### Scenario: Several products satisfy one ingredient

- **WHEN** more than one product satisfies an ingredient
- **THEN** all of them can be associated with it, because which is cheapest changes from day to day and the cheapest is the point

#### Scenario: Proposing never blocks adopting

- **WHEN** a recipe is adopted
- **THEN** its ingredients are resolved as far as they can be automatically, and the person is not asked to approve anything before the recipe exists

#### Scenario: A resolution is reused

- **WHEN** an ingredient that has already been resolved appears in a newly adopted recipe
- **THEN** the existing resolution applies without being asked for again

### Requirement: An unresolvable ingredient is visible, not silent

Where an ingredient cannot be resolved to any product, the recipe SHALL still be adopted, and the gap SHALL be visible wherever that recipe's cost is used. The system SHALL NOT drop the ingredient, guess at it, or present a cost as complete when it is not.

#### Scenario: One ingredient cannot be matched

- **WHEN** a recipe is adopted and one of its ingredients matches no product
- **THEN** the recipe is still added, with that ingredient recorded as unresolved

#### Scenario: The cost of a partially resolved recipe

- **WHEN** a recipe with an unresolved ingredient is costed
- **THEN** the cost is presented as incomplete, and how much is missing is apparent

#### Scenario: Resolving it later

- **WHEN** an unresolved ingredient is later resolved
- **THEN** every recipe using it becomes complete, with no need to re-adopt any of them

### Requirement: Dependence on the retailer's interface fails loudly

The retailer's recipe interface is unofficial and has already lost one backend service. When it is unavailable or its shape changes, the system SHALL report that plainly and SHALL NOT present an absence of recipes as an absence of results.

#### Scenario: The interface is unavailable

- **WHEN** a search cannot reach the retailer
- **THEN** the person is told the catalogue is unreachable, distinctly from being told nothing matched

#### Scenario: The response is not the shape expected

- **WHEN** the retailer returns data the system cannot interpret
- **THEN** the failure is reported rather than producing a recipe with missing ingredients

#### Scenario: Recipes already adopted

- **WHEN** the retailer's interface is unavailable
- **THEN** recipes already adopted continue to work, because they are held locally
