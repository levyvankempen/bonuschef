## ADDED Requirements

### Requirement: Adding a recipe takes a search and a confirmation

The portal SHALL let a person add a recipe by searching, previewing and confirming it. Adding a recipe SHALL NOT require entering each ingredient separately, nor re-stating a choice the person has already made.

#### Scenario: Adding a recipe

- **WHEN** a person finds the recipe they want and confirms it
- **THEN** it is added, without them entering its ingredients one at a time

#### Scenario: Seeing it before committing

- **WHEN** a recipe is offered
- **THEN** its ingredients and serving count are visible before the person commits to it

#### Scenario: Selection is not restated

- **WHEN** a person picks something from a set of results
- **THEN** that act selects it, rather than requiring them to find the same item again in another control

#### Scenario: Nothing found

- **WHEN** a search returns no recipes
- **THEN** the person is told so, distinctly from the catalogue being unreachable

### Requirement: The portal finishes its own work

Where an action requires pipeline work to take effect, the portal SHALL carry it out and report the outcome. It SHALL NOT instruct the person to run a command elsewhere.

#### Scenario: After adding a recipe

- **WHEN** a person adds a recipe whose cost needs computing
- **THEN** the portal starts that work itself and shows the result when it completes

#### Scenario: The work fails

- **WHEN** the pipeline work fails
- **THEN** the failure is shown, and the recipe is not presented as priced

#### Scenario: No instructions to use a terminal

- **WHEN** any action completes
- **THEN** the portal does not ask the person to run a build command by hand
