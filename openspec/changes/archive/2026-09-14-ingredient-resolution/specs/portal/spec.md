## ADDED Requirements

### Requirement: Reviewing resolutions does not become a per-ingredient chore

The portal SHALL let a person settle an ingredient's resolution without that becoming a step in adopting a recipe. Reviewing SHALL be optional, SHALL present every outstanding ingredient together rather than one at a time, and SHALL arrive with the automatic proposals already chosen so that agreeing costs nothing.

#### Scenario: Adopting stays three steps

- **WHEN** a person adopts a recipe whose ingredients are not all resolved
- **THEN** the recipe is added without them being asked to resolve anything first

#### Scenario: Several outstanding ingredients

- **WHEN** a person chooses to review
- **THEN** every outstanding ingredient is shown together, and one action settles them

#### Scenario: Agreeing with the proposals

- **WHEN** the proposals shown are all correct
- **THEN** accepting them requires no selection, only confirmation

#### Scenario: Leaving it unresolved

- **WHEN** a person reviews an ingredient and chooses nothing
- **THEN** that is accepted as an answer rather than blocked as an incomplete form

### Requirement: A wrong match is correctable where it is visible

Wherever the portal shows which product an ingredient resolved to, it SHALL offer a way to change it. Correcting SHALL apply to the ingredient, so every recipe using it is corrected at once rather than recipe by recipe.

#### Scenario: Noticing a wrong product on a recipe

- **WHEN** a person sees that an ingredient resolved to the wrong product
- **THEN** they can correct it from there, without navigating elsewhere or re-adding the recipe

#### Scenario: The correction reaches other recipes

- **WHEN** an ingredient used by several recipes is corrected
- **THEN** all of them reflect the correction

#### Scenario: The cost follows

- **WHEN** a resolution changes
- **THEN** the affected recipe costs are recomputed without the person being asked to run anything
