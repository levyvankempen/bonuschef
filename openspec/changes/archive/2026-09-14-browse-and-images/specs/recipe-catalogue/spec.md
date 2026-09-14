## ADDED Requirements

### Requirement: The catalogue can be browsed, not only searched

The system SHALL be able to retrieve recipes from the catalogue without a search term, ordered by the orderings the catalogue itself supports — at least what is newest and what is most popular.

#### Scenario: Newest recipes

- **WHEN** recipes are requested ordered by recency
- **THEN** the catalogue's most recently published recipes are returned

#### Scenario: An unsupported ordering

- **WHEN** an ordering the catalogue does not support is requested
- **THEN** the request is rejected before it is sent rather than failing at the retailer

### Requirement: Recipes can be narrowed by the catalogue's own facets

The system SHALL be able to narrow recipes using the categories the catalogue defines, and SHALL obtain the available categories and their values from the catalogue rather than holding its own copy.

#### Scenario: Narrowing by season

- **WHEN** recipes are requested for a season
- **THEN** only recipes the catalogue places in that season are returned

#### Scenario: The facets change

- **WHEN** the catalogue adds, removes or renames a category value
- **THEN** the change is reflected without the system being altered, because the values are read from the catalogue

#### Scenario: Narrowing combined with an ordering

- **WHEN** a narrowing and an ordering are requested together
- **THEN** both are applied
