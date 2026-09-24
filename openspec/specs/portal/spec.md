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

### Requirement: The portal reports the health of the pipeline behind it

The portal SHALL show whether the work that produces its answers is still running, and SHALL say so when it is not. It SHALL NOT rely solely on the age of the source data, because a load that succeeds followed by a rebuild that fails leaves the source fresh and every answer frozen.

#### Scenario: A scheduled job stops succeeding

- **WHEN** a job that feeds the page has not succeeded within the period it runs on
- **THEN** the page says so, naming the job and when it last worked

#### Scenario: Everything is running

- **WHEN** every job is succeeding on its cadence
- **THEN** nothing is shown, because a health indicator that is always present is furniture

#### Scenario: The credential is the one that stopped

- **WHEN** the job that keeps the retailer credential alive has not succeeded recently
- **THEN** that is surfaced distinctly, because its recovery needs a browser and cannot be done unattended

#### Scenario: The warning does not depend on an alerting channel

- **WHEN** no notification channel is subscribed
- **THEN** the page still reports the failure, because it is then the only surface on which it can be noticed

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

### Requirement: An operator can see the state of what they run

The portal SHALL offer an operator a view of the accounts on it: for each, when
it was made, when it was last used, which shop it is connected to, and what it
has saved.

The view SHALL be reachable only by an operator. It SHALL NOT be listed for
other accounts, and SHALL refuse to render for them even if its address is
reached directly - a page hidden only by being unlinked is not access control.

It SHALL distinguish an account that has never been used from one that is
merely quiet, and an account with no shop from one whose shop is simply not
where the operator expected. Those are the two states that mean somebody got
stuck rather than lost interest.

#### Scenario: The operator opens the view

- **WHEN** an operator opens it
- **THEN** every account is listed with when it was created, when it was last used, its shop, and how many recipes it has saved

#### Scenario: Another account tries to reach it

- **WHEN** an account that is not an operator reaches the view's address directly
- **THEN** it does not render, and says nothing about what it would have shown

#### Scenario: It is not offered to people who cannot use it

- **WHEN** an account that is not an operator is signed in
- **THEN** the view is not listed among the places they can go

#### Scenario: An account that never got started

- **WHEN** an account has been created but never signed in, or has signed in but never chosen a shop
- **THEN** that is shown as its own state rather than as a blank or a zero

#### Scenario: What an account has saved

- **WHEN** the operator looks at one account
- **THEN** the recipes it has saved are named, with when each was saved and when it was last cooked

#### Scenario: No credential is shown

- **WHEN** any account is displayed
- **THEN** no password and no password hash appears anywhere on the page
