## ADDED Requirements

### Requirement: A person is not shown food they have said they do not eat

The portal SHALL let a person exclude an ingredient permanently, and SHALL NOT
recommend recipes containing it thereafter.

The exclusion SHALL be recorded against that account alone, SHALL be reversible,
and SHALL be reviewable in one place so it cannot quietly accumulate into an
empty page.

It SHALL be expressible where the dislike is felt - on a card offering the food -
and not only in a settings page visited later.

Because one food answers to many names, a person excluding one SHALL be told
what else that hides before it takes effect.

#### Scenario: Excluding an ingredient from a recommendation

- **WHEN** a person is shown a recipe containing food they do not eat
- **THEN** they can exclude that ingredient from where they are, without leaving the page

#### Scenario: A recipe containing an excluded ingredient

- **WHEN** a recipe contains an ingredient the person has excluded
- **THEN** it is not recommended to them, however cheap it is

#### Scenario: One food under several names

- **WHEN** an ingredient is excluded and the catalogue knows the same food by other names
- **THEN** the person is shown what else will be hidden before confirming, rather than discovering the exclusion was narrower than they meant

#### Scenario: Changing their mind

- **WHEN** a person reviews what they have excluded
- **THEN** they can remove any of it, and the recipes return

#### Scenario: One person's exclusion is their own

- **WHEN** one account excludes an ingredient
- **THEN** no other account's recommendations change

#### Scenario: Excluding so much that nothing is left

- **WHEN** exclusions leave no recipe to recommend
- **THEN** the page says that is why, rather than reading as having found nothing on offer

### Requirement: Changing which product an ingredient means is an operator's act

Where a decision about an ingredient's products applies to every account, only
an operator SHALL be able to make it.

The portal SHALL NOT offer that decision to an account that cannot make it, and
SHALL refuse it if reached by other means.

A match is shared: it is keyed on the retailer's ingredient concept so that
confirming one serves every recipe using it, which is what makes the review
worth doing - and is also what makes a stranger's guess able to change the price
on everybody else's card.

#### Scenario: An invited person sees a doubtful match

- **WHEN** an account that is not an operator views an ingredient matched to the wrong product
- **THEN** they are not offered a control that would change it for everyone

#### Scenario: Reaching the correction another way

- **WHEN** an account that is not an operator reaches the correction directly
- **THEN** it is refused, and nothing is written

#### Scenario: The operator corrects a match

- **WHEN** an operator corrects a match
- **THEN** it applies to every recipe using that ingredient, as it does today

## MODIFIED Requirements

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

The alternatives SHALL be chosen for being different answers, not for being the
next largest numbers. Where a saving rests on a single discounted ingredient -
which on live data is every ranked recipe - ordering by saving alone ranks
today's discounted products and prints each one's recipe list, so six cards
carry one fact. Measured: of the top twenty for one shop, eleven were the same
fish and five were bacon.

#### Scenario: Many recipes share one discounted ingredient

- **WHEN** several ranked recipes owe their saving to the same discounted ingredient
- **THEN** the alternatives shown are each driven by a different ingredient, rather than repeating one

#### Scenario: Seeing the rest of one ingredient's recipes

- **WHEN** a person wants the other recipes for an ingredient that was shown once
- **THEN** they can reach them, through the same control that already filters by ingredient rather than a second one

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

Where the page shows fewer recipes than it ranked - because it chose variety, or
because the person has excluded something - it SHALL say so. A count of what was
computed, beside a shorter list, is a page that misrepresents its own selection.

#### Scenario: The shortlist is narrower than the ranking

- **WHEN** fewer recipes are shown than were ranked
- **THEN** the page says how many were ranked, how many are shown, and why the rest are not

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

Where an ingredient is named as driving the saving, the card SHALL show what
that product costs now and what it ordinarily costs. A saving expressed only as
a difference cannot be checked against a shelf, and checking it against the
shelf is what the person is doing when they read it.

#### Scenario: Checking a card against the shelf

- **WHEN** a discounted ingredient is named on a card
- **THEN** its current price and its ordinary price are both shown there, without the ingredient list having to be opened

#### Scenario: An ordinary price that is no longer fresh

- **WHEN** the ordinary price being compared against was observed some days ago
- **THEN** that is said where the comparison is shown, because a stale reference makes the difference decorative

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

Diagnostics SHALL have somewhere to live. Removing them from a shopper's page
only works if an operator can still see them, so they move to the operator's own
surface rather than being deleted - with the exception of a failure that changes
what a shopper should buy, which stays where the shopper is.

#### Scenario: Where the diagnostics go

- **WHEN** pipeline detail is taken off a page used for shopping
- **THEN** it appears on the operator's surface instead, rather than ceasing to be visible

#### Scenario: A failure that changes what to buy

- **WHEN** a failure means the prices shown may be wrong
- **THEN** it is still said where the prices are, not only on the operator's surface
