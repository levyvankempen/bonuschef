# portal

## ADDED Requirements

### Requirement: Saved recipes are presented as a dashboard, not a list

The page that shows a person's recipes SHALL present them as cards carrying
enough to choose between them - at minimum the title, the current cost where
one can be computed, and when that person last made it.

The present page is a list with a detail pane below it, which answers "show me
this recipe" and not "what shall I cook", and the second question is the one
being asked.

#### Scenario: A person opens their recipes

- **WHEN** a person with saved recipes opens the page
- **THEN** each is shown as a card with its title, its cost where known, and when they last made it

#### Scenario: A recipe cannot be costed

- **WHEN** a saved recipe has ingredients that are unresolved
- **THEN** it still appears, showing that its cost is incomplete rather than being hidden or shown as free

#### Scenario: A person has saved nothing yet

- **WHEN** an account has no saved recipes
- **THEN** the page says so and offers the ways to add one, rather than rendering an empty grid

### Requirement: Recipes can be narrowed to those on offer now

The recipes page SHALL offer a filter that keeps only recipes with at least
one ingredient on promotion or on clearance for that person's store today, and
SHALL say which it matched on.

This is the whole premise of the application applied to the collection rather
than to one recipe at a time.

#### Scenario: A person filters to what is on offer

- **WHEN** a person applies the filter
- **THEN** only recipes with an ingredient on offer today for their store remain, each showing what it matched on

#### Scenario: Clearance is not current

- **WHEN** the clearance snapshot for that person's store is not from today
- **THEN** the filter narrows on promotions alone and says that it has done so, rather than matching on stale clearance

#### Scenario: Nothing is on offer

- **WHEN** no saved recipe has an ingredient on offer
- **THEN** that is stated, rather than presenting an empty grid that looks like a loading failure

### Requirement: A recipe can be saved from the page that suggested it

Where the portal recommends a recipe, it SHALL offer to save that recipe to
the signed-in person's collection from that page.

#### Scenario: A person likes a suggestion

- **WHEN** a person saves a recipe from the page that recommended it
- **THEN** it joins their collection without leaving the page, and the page shows that it is now saved

#### Scenario: The recipe is already saved

- **WHEN** a recommended recipe is already in the person's collection
- **THEN** that is shown instead of offering to save it again

### Requirement: A saved recipe can be edited

A person SHALL be able to change a saved recipe's ingredients, quantities and
notes, and the result SHALL be what that person sees everywhere afterwards.

#### Scenario: A person edits a recipe

- **WHEN** a person changes an ingredient or a quantity on a saved recipe
- **THEN** their cost and shopping figures reflect the change from then on

#### Scenario: An edit does not reach other accounts

- **WHEN** a person edits a recipe that came from the shared catalogue
- **THEN** other accounts continue to see it unchanged

#### Scenario: An edit introduces an unresolved ingredient

- **WHEN** an edit adds an ingredient that resolves to no product
- **THEN** the recipe is kept and the unresolved ingredient is shown as such, rather than the edit being refused
