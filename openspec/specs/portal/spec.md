# portal Specification

## Purpose

Governs how the portal presents pipeline-produced data to a person, so that what is shown carries an honest claim about its currency — particularly for data that perishes within hours of being collected.

## Requirements

### Requirement: Perishable data is not presented as current once stale

Where displayed data describes a fast-changing real-world state — store clearance items, whose discounts deepen through the day and whose stock sells out within hours — the portal SHALL NOT present a snapshot older than the current trading day as though it were current. It SHALL instead state that the data is stale, how old it is, and how to refresh it.

#### Scenario: The snapshot is from today

- **WHEN** the most recent snapshot was taken during the current trading day
- **THEN** the items are shown normally, alongside the time they were captured

#### Scenario: The snapshot is from a previous day

- **WHEN** the most recent snapshot predates the current trading day
- **THEN** the items are not presented as current, and the page states the snapshot's age and offers a refresh

#### Scenario: A stale snapshot is months old

- **WHEN** the most recent snapshot is many weeks old
- **THEN** the page is as clear about staleness as it is for a snapshot one day old, without needing a separate threshold

#### Scenario: No snapshot has ever been taken

- **WHEN** no clearance data exists at all
- **THEN** the page explains that none has been collected yet, distinctly from the case where data exists but is stale

#### Scenario: A refresh succeeds

- **WHEN** an operator refreshes and the scrape succeeds
- **THEN** the page presents the new items as current without a reload being needed

#### Scenario: A refresh fails

- **WHEN** an operator refreshes and the scrape fails
- **THEN** the failure is reported, and the stale data is still not presented as current

### Requirement: Data currency is stated wherever perishable data is shown

The portal SHALL show when a displayed snapshot was captured, in local time, whenever it presents perishable data — whether that data is fresh or stale.

#### Scenario: Fresh data is displayed

- **WHEN** current clearance items are shown
- **THEN** the capture time is visible without interaction

#### Scenario: Local time is used

- **WHEN** a capture time is displayed
- **THEN** it is rendered in Dutch local time, matching the store hours the data describes

### Requirement: Every destination is reachable without discovery

The portal SHALL present its destinations visibly at all times. Navigation SHALL NOT depend on the user first opening a hidden region, and each destination SHALL be identifiable at a glance.

#### Scenario: The portal is opened

- **WHEN** a person opens the portal on any device
- **THEN** every destination is visible without opening or expanding anything

#### Scenario: Arriving on a phone

- **WHEN** the viewport is narrow
- **THEN** navigation remains visible and usable, rather than collapsing into a control that must be found

#### Scenario: The interface language

- **WHEN** any label, heading or message is shown
- **THEN** it is in one language throughout, matching the language of the domain the data describes

### Requirement: Lists read in a shop are legible on a phone

Where the portal presents a list a person reads while shopping, each entry SHALL be legible on a narrow screen without horizontal scrolling, and SHALL lead with the facts that drive the decision: what the item is, what it now costs, and what makes it urgent.

#### Scenario: Clearance items on a narrow screen

- **WHEN** clearance items are shown on a phone
- **THEN** each entry is readable without scrolling sideways, and its current price is the most prominent figure

#### Scenario: An item that is nearly gone

- **WHEN** an item has very little stock left, or expires today
- **THEN** that is visible on the entry itself, because it is the reason to act now rather than later

#### Scenario: Imagery already available is used

- **WHEN** a product image has already been retrieved for an item
- **THEN** it is shown, rather than fetched and discarded

#### Scenario: Ordering serves the decision

- **WHEN** a list of perishable discounted items is ordered
- **THEN** the ordering reflects what is most likely to be gone, not only the largest percentage

### Requirement: The portal shows its user the product, not the pipeline

The portal SHALL NOT present measures that describe the health of its own data pipeline — match rates, join coverage, row counts of internal reconciliation — as though they were information about groceries. Internal diagnostics MAY remain available, but SHALL NOT occupy the primary surfaces.

#### Scenario: A join coverage statistic

- **WHEN** a page would show how many records matched between two internal sources
- **THEN** that figure is not presented to the user as a headline measure

#### Scenario: A raw internal value

- **WHEN** a value from the warehouse has a code or boolean form used internally
- **THEN** it is translated for display, or not shown

#### Scenario: The insight behind the diagnostics survives

- **WHEN** a retailer's advertised saving exceeds the saving measured against observed prices
- **THEN** that discrepancy is still communicated, in the place where the saving is shown, rather than in a separate table of internals

### Requirement: A rendering does not cost more than the data it shows

Rendering a page SHALL NOT perform work disproportionate to what it displays. In particular the portal SHALL NOT make blocking network calls to third parties during rendering, SHALL NOT issue schema-changing statements on each interaction, and SHALL NOT retrieve unbounded result sets to display a bounded view.

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

### Requirement: Nothing is displayed twice in two forms

The portal SHALL NOT present the same small set of values both as a figure and as a chart of those same figures. A visualisation SHALL earn its place by showing something the adjacent text does not.

#### Scenario: A handful of values

- **WHEN** a page shows a small number of values as text
- **THEN** it does not also plot those same values beside them

#### Scenario: A trend a person acts on

- **WHEN** a visualisation shows a pattern over time that changes a decision
- **THEN** it is retained

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

### Requirement: A list meant for recognition carries its imagery

Where the portal shows items a person matches against physical objects — products on a shelf, dishes to cook — it SHALL show the image the source provides. Where the source provides an image and the portal does not display it, that is a defect rather than a choice.

#### Scenario: Clearance items on a phone

- **WHEN** clearance items are shown
- **THEN** each carries its product image, so the list can be recognised rather than read

#### Scenario: The source has no image for an item

- **WHEN** no image is available for an item
- **THEN** the entry still renders, without a gap where a picture would be

#### Scenario: Imagery is not fetched while rendering

- **WHEN** images are shown
- **THEN** they were obtained when the data was collected, not requested from a third party during the render

### Requirement: Finding a recipe does not require knowing its name

The portal SHALL let a person find a recipe without first typing a search term. It SHALL offer the catalogue's own recipes on arrival, ordered by something useful, and SHALL let that ordering be changed.

#### Scenario: Arriving with nothing in mind

- **WHEN** a person opens the page to add a recipe and types nothing
- **THEN** recipes are already shown, and any of them can be adopted

#### Scenario: Choosing what to see

- **WHEN** a person wants what is new rather than what is popular
- **THEN** the ordering can be changed between the options the catalogue supports

#### Scenario: Searching still works

- **WHEN** a person types a search term
- **THEN** the results for that term replace the browsable list

#### Scenario: The catalogue is unreachable

- **WHEN** the catalogue cannot be reached on arrival
- **THEN** the person is told so, rather than shown an empty page that reads as having no recipes
