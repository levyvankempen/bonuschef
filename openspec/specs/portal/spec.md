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

Reporting the outcome SHALL NOT depend on the person's session surviving the work. The state SHALL be read from the run itself, so that a session which was interrupted still learns how it went.

Work that is waiting to start SHALL be distinguishable from work that is running.

#### Scenario: After adding a recipe

- **WHEN** a person adds a recipe whose cost needs computing
- **THEN** the portal starts that work itself and shows the result when it completes

#### Scenario: The work fails

- **WHEN** the pipeline work fails
- **THEN** the failure is shown, and the recipe is not presented as priced

#### Scenario: No instructions to use a terminal

- **WHEN** any action completes
- **THEN** the portal does not ask the person to run a build command by hand

#### Scenario: The work has not started yet

- **WHEN** requested work is waiting behind other work
- **THEN** the page says it is waiting rather than describing it as under way

#### Scenario: The session is interrupted while work runs

- **WHEN** a person leaves the page, or their session drops, before the work finishes
- **THEN** returning to the page reports how the work went, rather than showing no trace of it

#### Scenario: A completed refresh reaches every reader

- **WHEN** pipeline work finishes and changes what a page would show
- **THEN** the page reflects it without waiting for a cache to expire, including for a session that did not request the work

#### Scenario: Success is not confused with change

- **WHEN** requested work completes without altering the data
- **THEN** the page does not claim the data is newer than it is

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

### Requirement: The portal answers what to cook tonight

The portal SHALL have a destination that answers, in one view, which recipe is most worth cooking today and why. It SHALL name the ingredients that became cheaper, what they now cost, and what makes any of them urgent.

#### Scenario: There is a clear best option

- **WHEN** one recipe is markedly cheaper today than it ordinarily is
- **THEN** it is presented first and in full, with the ingredients responsible named

#### Scenario: Several are worth considering

- **WHEN** more than one recipe is cheaper today
- **THEN** the others are listed below, briefly, without competing with the first for attention

#### Scenario: A saving that is only partly known

- **WHEN** the best recipe is not fully priced
- **THEN** its saving is shown as a lower bound, and its cost is shown as an estimate marked as one, never as a total

#### Scenario: An estimate says what it rests on

- **WHEN** a cost is shown for an incompletely priced recipe
- **THEN** how many of its ingredients the figure covers is shown with it, so a low number is read as incomplete rather than as cheap

#### Scenario: Nothing is priced at all

- **WHEN** none of a recipe's ingredients has a known price
- **THEN** no figure is shown, because there is nothing to estimate from

#### Scenario: Nothing is a bargain today

- **WHEN** no recipe is meaningfully cheaper
- **THEN** the person is told so plainly, and still offered something useful rather than an empty page

#### Scenario: Nothing has been adopted yet

- **WHEN** a person has no recipes of their own
- **THEN** the page explains what it would show and offers the one action that would make it work

### Requirement: The page degrades by withdrawing evidence, not by going blank

WHEN clearance is no longer current, the page SHALL re-rank on promotional pricing alone and say that it has done so, rather than refusing to answer. It SHALL NOT present a clearance price as presently available once the snapshot it came from is no longer from the current trading day.

#### Scenario: Clearance has aged out but promotions have not

- **WHEN** the clearance snapshot is from a previous trading day
- **THEN** the page ranks on promotions alone, removes clearance prices from the ingredients it names, and states that clearance was set aside

#### Scenario: The promotional feed itself is stale

- **WHEN** the promotional feed has not been refreshed within the period it covers
- **THEN** that is said, and the ranking is not presented as describing this week

#### Scenario: The warehouse cannot be reached

- **WHEN** the page cannot read the warehouse at all
- **THEN** it says so in the same terms the rest of the portal uses, and offers the action that would fix it

### Requirement: The page is honest about how much it can see

The portal SHALL show how many recipes are held and how many of them can presently be ranked, and SHALL make the reason a recipe is not ranked reachable rather than leaving it absent without explanation.

#### Scenario: The pool is much larger than the rankable set

- **WHEN** most held recipes cannot be ranked because their ingredients are unresolved
- **THEN** both counts are visible, so the ranking is not read as covering everything held

#### Scenario: Finding out why a recipe is missing

- **WHEN** a person looks for a recipe that is not in the ranking
- **THEN** the reason it was not ranked is reachable from the page

#### Scenario: The most useful next action is offered

- **WHEN** recipes are unrankable for want of resolved ingredients
- **THEN** the page offers the ingredient review that would make the most of them rankable

### Requirement: A machine-proposed match is visible and correctable where it is used

Where an ingredient's product was matched automatically rather than chosen by a person, the page SHALL show which product the figure rests on and SHALL offer to correct it from the same place. A person SHALL NOT have to leave the answer to find out what it was computed from.

#### Scenario: Reading what a price rests on

- **WHEN** a recipe's ingredients are shown
- **THEN** each one names the product it is matched to, whether or not that ingredient is discounted

#### Scenario: A wrong match

- **WHEN** a person sees that an ingredient is matched to the wrong product
- **THEN** they can correct it from that line, and the correction applies to every recipe using that ingredient

#### Scenario: The ingredient list is the list

- **WHEN** the ingredients of a recipe are opened
- **THEN** all of them are shown, not only the ones that became cheaper

### Requirement: The page states what a figure covers

The portal SHALL NOT present a saving in a way that implies it was saved on the meal when it was saved on a whole pack the meal uses part of, and SHALL NOT include a conditional promotional price in a stated saving.

#### Scenario: A saving on a pack used sparingly

- **WHEN** a recipe uses part of a discounted pack
- **THEN** the figure is described as covering the whole pack

#### Scenario: An ingredient on a multibuy promotion

- **WHEN** an ingredient's promotional price requires buying more than the recipe needs
- **THEN** it is shown separately with its condition stated, and is not part of the ranked saving

### Requirement: The page lets a person curate what it recommends

The portal SHALL offer, on each recommended recipe, a way to keep it and a way to reject it, and SHALL make what has been rejected reviewable and reversible.

#### Scenario: Dismissing a recipe from the ranking

- **WHEN** a person rejects a recommended recipe
- **THEN** it leaves the ranking immediately and does not return

#### Scenario: Keeping one worth cooking again

- **WHEN** a person keeps a recommended recipe
- **THEN** it joins their own recipes and survives every later pool refresh

#### Scenario: Reviewing what was dismissed

- **WHEN** a person wants to see what they have rejected
- **THEN** the list is reachable from the page and each entry can be reinstated

#### Scenario: The rating is shown with its weight

- **WHEN** a pool recipe's rating is shown
- **THEN** the number of votes behind it is shown with it

### Requirement: The page is the portal's default destination

The portal SHALL open on this page, because it is the question the rest of the application exists to support.

#### Scenario: Opening the application

- **WHEN** a person opens the portal
- **THEN** this page is what they arrive at, with the existing destinations still reachable
