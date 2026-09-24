## ADDED Requirements

### Requirement: A recommendation is recognised before it is read

Where the portal recommends a recipe, the recommendation SHALL be presented as a
card whose image is its first and widest element, and whose largest text is the
saving. The dish is identified by sight in less than a second; the saving is the
reason to act. Neither is served by a thumbnail beside a paragraph.

The card SHALL also name the discounted ingredients that produce the saving,
rather than only counting them. A person in the shop is standing in front of one
of them.

#### Scenario: A recommended recipe on a phone

- **WHEN** a recipe is recommended
- **THEN** its image spans the width of the card and appears before any text, and the saving is the largest text on the card

#### Scenario: Why this recipe is cheap

- **WHEN** a recipe's saving comes from particular discounted ingredients
- **THEN** those ingredients are named on the card, with what each saves, in decreasing order of saving

#### Scenario: More discounted ingredients than the card can carry

- **WHEN** a recipe has more discounted ingredients than the card shows
- **THEN** the largest savings are the ones named, and the remainder are indicated as a count rather than silently dropped

#### Scenario: A saving that is a lower bound

- **WHEN** a recipe's cost coverage is partial
- **THEN** the saving keeps the wording that marks it a lower bound, and does not become an exact figure by being made prominent

#### Scenario: A recipe with no image

- **WHEN** the source provides no image for a recommended recipe
- **THEN** the card still renders, led by its title, without a gap where the image would be

#### Scenario: One recommendation per row

- **WHEN** recommendations are laid out
- **THEN** each occupies the full width available, because a column that is split does not narrow on a phone and would halve the image instead

### Requirement: A person can start from an ingredient

The portal SHALL let a person find recipes by an ingredient rather than by a
recipe's name, over the recipes it ranks rather than only those already saved.
The question asked in a shop is "this is discounted, what do I cook with it",
and it SHALL be answerable without typing.

#### Scenario: Starting from what is discounted today

- **WHEN** a person opens the page that answers what to cook
- **THEN** the ingredients discounted today are offered as direct choices, so that finding a recipe for one costs a single tap and no typing

#### Scenario: Naming an ingredient

- **WHEN** a person names an ingredient
- **THEN** the recommendations narrow to recipes using it, keeping the order and the price rules they already had

#### Scenario: An ingredient is matched by what it is called and by what is on the shelf

- **WHEN** a person names an ingredient
- **THEN** both the recipe's own word for it and the matched product's name are searched, because the shelf label and the recipe rarely agree

#### Scenario: Nothing on offer uses it

- **WHEN** no recommended recipe uses the named ingredient
- **THEN** the page says so in terms of that ingredient, and still offers the cheapest recipes using it, rather than showing an empty page

#### Scenario: Asking for nothing

- **WHEN** no ingredient is named and none is chosen
- **THEN** the page shows exactly what it shows today, unfiltered

### Requirement: A search term is data, not a pattern

Where the portal accepts a term typed by a person, it SHALL treat that term as
literal text. A term SHALL NOT be interpreted as a pattern, and no term SHALL be
able to fail the page.

#### Scenario: A term containing pattern punctuation

- **WHEN** a person searches for a term containing characters such as `(`, `+`, `*` or `[`
- **THEN** those characters match themselves, and the page does not fail

### Requirement: Destroying a saved recipe is confirmed

Where the portal offers an action that permanently removes a person's own data,
that action SHALL require a confirming step. It SHALL NOT be a single tap
adjacent to a routine control.

#### Scenario: Deleting a saved recipe

- **WHEN** a person deletes a saved recipe
- **THEN** the deletion takes a confirming step before it happens

#### Scenario: A deletion sits beside an everyday action

- **WHEN** a destructive control is placed beside one used routinely
- **THEN** the destructive one is not reachable in the same single tap as its neighbour

## MODIFIED Requirements

### Requirement: A list meant for recognition carries its imagery

Where the portal shows items a person matches against physical objects — products on a shelf, dishes to cook — it SHALL show the image the source provides. Where the source provides an image and the portal does not display it, that is a defect rather than a choice.

An image SHALL be shown at a size at which the thing is recognisable at arm's
length, and SHALL NOT be enlarged past the resolution the source actually
publishes. A picture scaled beyond its source is worse than a smaller sharp one.

#### Scenario: Clearance items on a phone

- **WHEN** clearance items are shown
- **THEN** each carries its product image, so the list can be recognised rather than read

#### Scenario: The source has no image for an item

- **WHEN** no image is available for an item
- **THEN** the entry still renders, without a gap where a picture would be

#### Scenario: Imagery is not fetched while rendering

- **WHEN** images are shown
- **THEN** they were obtained when the data was collected, not requested from a third party during the render

#### Scenario: The source publishes more than one size

- **WHEN** the source publishes an image in several sizes
- **THEN** the one shown is the largest that is useful at the size it is displayed, rather than the smallest that exists

#### Scenario: A display larger than the source

- **WHEN** the space available is wider than the largest image the source publishes
- **THEN** the image is not stretched to fill it

### Requirement: A rendering does not cost more than the data it shows

Rendering a page SHALL NOT perform work disproportionate to what it displays. In particular the portal SHALL NOT make blocking network calls to third parties during rendering, SHALL NOT issue schema-changing statements on each interaction, and SHALL NOT retrieve unbounded result sets to display a bounded view.

Detail a person has not asked to see SHALL NOT be built. A closed section
SHALL add no query of its own and SHALL register no controls until it is
opened. Where the same data already serves something the card does show, it is
read once and shared rather than fetched twice.

#### Scenario: A page with several items

- **WHEN** a page renders a list of items whose images are already known
- **THEN** no third-party request is made while rendering

#### Scenario: Typing in a search field

- **WHEN** a person types into a search field
- **THEN** the interaction does not cause schema-changing statements to run

#### Scenario: Displaying a bounded view of a large table

- **WHEN** a page shows a limited view of a large table
- **THEN** the query retrieving it is bounded too, rather than fetching every row and reducing afterwards

#### Scenario: Data that changes slowly

- **WHEN** displayed data only changes when a pipeline runs
- **THEN** it is not re-queried on a cadence far shorter than the pipeline's, and an explicit refresh still takes effect immediately

#### Scenario: A detail section nobody opened

- **WHEN** a page offers per-recipe detail that is closed on arrival
- **THEN** its controls are not registered until a person opens it, and it issues no query beyond what the visible part of the card already reads

### Requirement: Saved recipes are presented as a dashboard, not a list

The page that shows a person's recipes SHALL present them as cards carrying
enough to choose between them - at minimum the title, the current cost where
one can be computed, and when that person last made it.

A saved recipe is chosen between the same way a recommended one is, so its card
SHALL be led by its image on the same terms.

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

#### Scenario: A saved recipe carries its picture

- **WHEN** a saved recipe has an image
- **THEN** its card is led by that image, as a recommended recipe's card is
