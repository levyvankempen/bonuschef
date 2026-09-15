## ADDED Requirements

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
