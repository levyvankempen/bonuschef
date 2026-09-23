# recipe-catalogue Specification

## Purpose

Defines how a recipe enters the system without being typed, and how its ingredients acquire an identity that can be priced — so that going from two recipes to twenty costs minutes rather than an evening, and so that an ingredient nobody can price is visibly unpriced rather than quietly absent.

## Requirements

### Requirement: A recipe can be adopted from the retailer's catalogue

A person SHALL be able to add a recipe by finding it in the retailer's own catalogue rather than by entering it. An adopted recipe SHALL carry its title, its serving count, and each ingredient with the quantity the recipe calls for.

#### Scenario: Finding a recipe by name

- **WHEN** a person searches the catalogue for a dish
- **THEN** matching recipes are offered, identified well enough to choose between them

#### Scenario: Adopting a recipe

- **WHEN** a person adopts a recipe from the results
- **THEN** it becomes one of their recipes, with its ingredients and quantities, without further typing

#### Scenario: The same recipe twice

- **WHEN** a person adopts a recipe they already have
- **THEN** they are not given a duplicate

#### Scenario: A hand-entered recipe

- **WHEN** a person enters a recipe of their own rather than adopting one
- **THEN** it is treated the same way everywhere downstream; adoption is an additional path, not a replacement

### Requirement: Ingredients carry a reusable identity

An ingredient SHALL be recorded against the retailer's stable identity for that ingredient, not only as text. Where two recipes call for the same ingredient, they SHALL share that identity, so effort spent resolving it is spent once.

#### Scenario: An ingredient shared between recipes

- **WHEN** two adopted recipes each call for the same ingredient
- **THEN** both reference the same ingredient identity, and resolving it once serves both

#### Scenario: A variant is a distinct ingredient

- **WHEN** the catalogue distinguishes a variant of an ingredient from its ordinary form
- **THEN** that distinction is preserved rather than collapsed, because the two have different prices and availability

#### Scenario: The retailer's text still travels with it

- **WHEN** an ingredient is recorded
- **THEN** its human-readable name is kept alongside the identity, so a person can read a recipe without a lookup

### Requirement: An ingredient is resolved to purchasable products explicitly

An ingredient identity SHALL be resolved to the products that satisfy it. The system SHALL propose candidates automatically, and a proposal SHALL persist and be reused by every recipe sharing that ingredient. Proposing SHALL NOT interrupt adoption: a person who adopts twenty recipes SHALL not be asked twenty times.

#### Scenario: A confident candidate

- **WHEN** the system finds a product that clearly satisfies an ingredient
- **THEN** it is proposed as the resolution, and accepting it requires no work

#### Scenario: Several products satisfy one ingredient

- **WHEN** more than one product satisfies an ingredient
- **THEN** all of them can be associated with it, because which is cheapest changes from day to day and the cheapest is the point

#### Scenario: Proposing never blocks adopting

- **WHEN** a recipe is adopted
- **THEN** its ingredients are resolved as far as they can be automatically, and the person is not asked to approve anything before the recipe exists

#### Scenario: A resolution is reused

- **WHEN** an ingredient that has already been resolved appears in a newly adopted recipe
- **THEN** the existing resolution applies without being asked for again

### Requirement: An unresolvable ingredient is visible, not silent

Where an ingredient cannot be resolved to any product, the recipe SHALL still be adopted, and the gap SHALL be visible wherever that recipe's cost is used. The system SHALL NOT drop the ingredient, guess at it, or present a cost as complete when it is not.

#### Scenario: One ingredient cannot be matched

- **WHEN** a recipe is adopted and one of its ingredients matches no product
- **THEN** the recipe is still added, with that ingredient recorded as unresolved

#### Scenario: The cost of a partially resolved recipe

- **WHEN** a recipe with an unresolved ingredient is costed
- **THEN** the cost is presented as incomplete, and how much is missing is apparent

#### Scenario: Resolving it later

- **WHEN** an unresolved ingredient is later resolved
- **THEN** every recipe using it becomes complete, with no need to re-adopt any of them

### Requirement: Dependence on the retailer's interface fails loudly

The retailer's recipe interface is unofficial and has already lost one backend service. When it is unavailable or its shape changes, the system SHALL report that plainly and SHALL NOT present an absence of recipes as an absence of results.

#### Scenario: The interface is unavailable

- **WHEN** a search cannot reach the retailer
- **THEN** the person is told the catalogue is unreachable, distinctly from being told nothing matched

#### Scenario: The response is not the shape expected

- **WHEN** the retailer returns data the system cannot interpret
- **THEN** the failure is reported rather than producing a recipe with missing ingredients

#### Scenario: Recipes already adopted

- **WHEN** the retailer's interface is unavailable
- **THEN** recipes already adopted continue to work, because they are held locally

### Requirement: A person can correct how an ingredient resolves

A person SHALL be able to change which products satisfy an ingredient, and their decision SHALL persist. An automatic proposal SHALL NOT overwrite a decision a person has made, however many times the matcher runs afterwards.

#### Scenario: Correcting a wrong proposal

- **WHEN** a person replaces the products proposed for an ingredient
- **THEN** the replacement is what every recipe using that ingredient costs against, for every account, because which product satisfies an ingredient is a fact about the catalogue rather than a preference

#### Scenario: The matcher runs again

- **WHEN** the automatic matcher runs over an ingredient a person has already decided
- **THEN** the person's decision stands, and the matcher does not silently revert it

#### Scenario: Filling a gap the matcher left

- **WHEN** the matcher runs over an ingredient nobody has decided
- **THEN** it may add products, because an untouched proposal is not a decision

#### Scenario: A decision is distinguishable from a guess

- **WHEN** a resolution is inspected
- **THEN** whether a person chose it or the matcher proposed it is apparent

### Requirement: An ingredient with no purchasable equivalent can be recorded as such

A person SHALL be able to record that nothing in the catalogue satisfies an ingredient. That state SHALL be distinguishable from an ingredient nobody has examined yet, and SHALL NOT be undone by the matcher.

#### Scenario: Nothing satisfies it

- **WHEN** a person concludes that no product corresponds to an ingredient
- **THEN** that conclusion is recorded, and the ingredient stops appearing as outstanding work

#### Scenario: Still unexamined

- **WHEN** an ingredient has never been reviewed
- **THEN** it is distinguishable from one a person has examined and found nothing for

#### Scenario: The cost stays honest either way

- **WHEN** a recipe contains an ingredient with no purchasable equivalent
- **THEN** its cost is still reported as incomplete, because an ingredient that cannot be bought is not an ingredient that is free

### Requirement: A recipe costs the cheapest product that satisfies each ingredient

Where several products satisfy an ingredient, the cost SHALL use the cheapest one whose price is known. Products whose price is unknown SHALL NOT be treated as cheaper than those whose price is known.

#### Scenario: Several products, different prices

- **WHEN** an ingredient resolves to more than one product
- **THEN** the recipe costs the cheapest of them

#### Scenario: One of them has no known price

- **WHEN** some of the products satisfying an ingredient have no observed price
- **THEN** the cheapest priced one is used, rather than the unpriced one being taken as free

#### Scenario: None of them has a known price

- **WHEN** no product satisfying an ingredient has an observed price
- **THEN** the ingredient counts as unpriced and the recipe's total is withheld

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

### Requirement: A product carries what kind of thing it is

A product SHALL carry the retailer's own classification of it — its taxonomy
path and the department of the store it is sold from — alongside its name and
price.

A name says what a product is called. A classification says what it is. The
two are not the same, and resolution has until now had only the first.

#### Scenario: Classification is available wherever a product is

- **WHEN** a product is considered as a candidate for an ingredient
- **THEN** what kind of thing it is can be read, without a further request to the retailer

#### Scenario: The retailer does not classify a product

- **WHEN** a product carries no classification
- **THEN** it is still usable, and the checks that depend on classification abstain rather than rejecting it

### Requirement: A candidate whose kind contradicts the ingredient is not proposed

A product SHALL NOT be proposed for an ingredient when its classification
contradicts what the ingredient is.

A food ingredient SHALL NOT be resolved by a non-food product. An ingredient
that asks for something fresh SHALL NOT be resolved by a product the retailer
sells as ambient or dried, and the reverse SHALL also hold.

These are not close calls. A live audit found a paper napkin resolving
"wortel", cough syrup resolving "kropje babyromainesla", and menstrual
painkillers resolving "runderbouillon van tablet" — each arrived at by a
confident name match.

#### Scenario: A non-food product matches the name

- **WHEN** a product outside the food departments carries the ingredient's name in its title
- **THEN** it is not proposed, because an ingredient cannot be satisfied by something inedible

#### Scenario: An ingredient asks for fresh

- **WHEN** an ingredient names a fresh form and a candidate is sold as a dried or ambient product
- **THEN** that candidate is not proposed, so "verse dille" is not satisfied by dried dill in a jar

#### Scenario: The ingredient says nothing about form

- **WHEN** an ingredient does not state a form
- **THEN** no candidate is rejected on that basis, because silence is not a requirement

### Requirement: A candidate the taxonomy names is preferred to one that merely mentions it

Where a candidate's classification names the ingredient, it SHALL be preferred
to a candidate whose title merely contains the ingredient's name.

A product classified as "Witte kaas" is white cheese. A product whose title
contains "witte kaas" may be a cheeseboard accompaniment, a dressing, or a
salami.

#### Scenario: The taxonomy names the ingredient

- **WHEN** one candidate is classified under the ingredient's own name and another only mentions it
- **THEN** the classified one is proposed ahead of the other

#### Scenario: Nothing is classified under the ingredient

- **WHEN** no candidate's classification names the ingredient
- **THEN** the existing ordering decides, so this preference adds an answer and never removes one

### Requirement: A candidate that is not recognisably the ingredient is not proposed

Where the best candidate for an ingredient is not recognisable as that
ingredient, no candidate SHALL be proposed and the ingredient SHALL be shown
as unresolved.

A candidate is recognisable when its classification names the ingredient, or
when the head nouns of the ingredient and the product agree. Either alone
suffices.

Ranking always produces a winner, even when every candidate is wrong. "Blauwe
kaas-blokjes" was priced as AH Blauwe bessen and "salade-uitjes" as AH Ei
salade: both food, both fresh, both sharing a word with the ingredient, so
every rule about kind and form accepted them. A cost built on those is worse
than no cost, because it looks right.

The test is deliberately about naming rather than degree of confidence. A
numeric floor was measured against the human-confirmed links and did not
separate: confirmed products scored as low as -1.20 while correct matches that
happened not to be confirmed scored 10.00, so every cut that removed a wrong
answer removed good ones too.

#### Scenario: The best candidate shares a word but is a different product

- **WHEN** the best candidate is neither named by its classification nor in head-noun agreement with the ingredient
- **THEN** nothing is proposed, and the ingredient is shown as unresolved rather than priced

#### Scenario: Only the product's name identifies it

- **WHEN** a candidate's classification is broader than the ingredient but its name agrees
- **THEN** it is proposed, because either evidence suffices

#### Scenario: The ingredient is written as a diminutive

- **WHEN** a recipe names an ingredient in a diminutive form and the product carries the plain noun
- **THEN** they are recognised as the same thing, because recipes routinely use diminutives the shelf label does not

#### Scenario: The ingredient is a compound of the product's general term

- **WHEN** an ingredient's name ends in the word its candidate is named by, or the reverse
- **THEN** they are recognised as the same thing, because a compound names its head last

#### Scenario: A person already confirmed the pairing

- **WHEN** a recorded resolution was confirmed by a person
- **THEN** it stands regardless of whether any rule can recognise it, because some correct pairings share no word at all

### Requirement: Only candidates of the same kind as the best one are proposed

Where several products are proposed for one ingredient, they SHALL all be the
same kind of thing as the best of them.

Proposing everything a search returns is not harmless. The cheapest candidate
decides a recipe's cost, so a single wrong candidate can decide it — a cream
cheese among the shallots sets the price of a dish containing no cream cheese.

#### Scenario: One candidate is a different kind of thing

- **WHEN** a search returns products of which some are the ingredient and some merely mention it
- **THEN** only those of the same kind as the best match are proposed

#### Scenario: Several genuinely interchangeable products

- **WHEN** several proposed products are the same kind of thing
- **THEN** all of them are kept, because which is cheapest changes from day to day and that is the point

#### Scenario: The best candidate is unclassified

- **WHEN** the best candidate carries no classification to compare against, but is recognisable as the ingredient by name
- **THEN** nothing is narrowed, because there is no evidence on which to narrow it

#### Scenario: The best candidate is unclassified and unrecognisable

- **WHEN** the best candidate carries no classification and is not recognisable as the ingredient by name either
- **THEN** nothing is proposed at all, because narrowing and withholding are different decisions and only the second one applies

### Requirement: Resolutions already recorded are re-checked

Resolutions already in the system SHALL be checked against classification when
it becomes available, and those that contradict it SHALL be surfaced for
review. The check SHALL apply the same recognisability test as a new proposal.

A check applied only to new proposals leaves every wrong answer already
recorded in place, which is where the known wrong answers actually are. A
check that examines only form and department leaves the ones that agree on
both: AH Blauwe bessen and "blauwe kaas-blokjes" are both food and both fresh.

#### Scenario: An existing resolution contradicts its classification

- **WHEN** a recorded resolution is found to contradict what its product is
- **THEN** it is raised for review rather than silently kept or silently deleted

#### Scenario: A concept a person already settled is found to be wrong

- **WHEN** a concept that was reviewed is later found to contradict itself
- **THEN** it returns to the queue of things to look at, ahead of ingredients that were never linked at all

#### Scenario: A wrong link is described differently from a missing one

- **WHEN** an ingredient is linked to a product that contradicts it
- **THEN** it is presented as a price that is wrong rather than as a gap, because the recipe already shows a cost and nothing otherwise looks amiss

#### Scenario: Everything is linked but some links are wrong

- **WHEN** no ingredient is unlinked but some links contradict themselves
- **THEN** the way to review them is still offered

#### Scenario: A flagged concept is settled

- **WHEN** a person confirms a resolution for a flagged concept
- **THEN** it stops being flagged, rather than returning to the head of the queue they just cleared it from

#### Scenario: A person has already decided

- **WHEN** a recorded resolution was confirmed by a person
- **THEN** it is left alone, because a human decision outranks a classification rule

#### Scenario: The only recorded product is a non-food one

- **WHEN** an ingredient's only recorded product is one it can never be satisfied by
- **THEN** that resolution is withdrawn even though nothing replaces it, because an ingredient with no product is already shown as unresolved, while a wrong one is silently priced

#### Scenario: The only recorded product is merely the wrong form

- **WHEN** an ingredient's only recorded product is edible but in a form the ingredient did not ask for
- **THEN** it is kept and raised for review, because a worse match is not an impossible one

#### Scenario: The only recorded product is not the ingredient at all

- **WHEN** an ingredient's only recorded product is edible and of the right form, but is not recognisable as the ingredient
- **THEN** that resolution is withdrawn even though nothing replaces it, and the concept is flagged, because this is the wrong product rather than a worse one

#### Scenario: A recorded product cannot be classified

- **WHEN** a recorded product is one the retailer no longer classifies
- **THEN** it is left alone, because unknown is not wrong

### Requirement: A person reviewing a match can see what each candidate is

When a person is choosing between candidate products for an ingredient, each
candidate SHALL show what kind of thing it is.

#### Scenario: Choosing between similarly named products

- **WHEN** several candidates carry similar names
- **THEN** what distinguishes them is visible without opening the retailer's website

### Requirement: An ingredient is searched for by what it is, not how it is sold

Where an ingredient names the container it comes in, the search for products
SHALL also be made without it.

The container word is matched by the retailer's own search, which then returns
the packaging rather than the food: "cannellinibonen in blik" returns tuna,
corn and pineapple, and "runderbouillon van tablet" returns Ibuprofen and
Paracetamol, both sold as tabletten. Removing the container returns the bean
and the stock.

#### Scenario: An ingredient names its container

- **WHEN** an ingredient names the container it is sold in
- **THEN** products are also sought for the ingredient without it, and the results of both are considered

#### Scenario: A qualifier that is not a container

- **WHEN** an ingredient names what it is packed in rather than what it is packed as
- **THEN** it is kept, because tuna in oil and tuna in water are different products and a recipe asking for one means it

### Requirement: The retailer's own label is preferred between equivalent products

Where two products satisfy an ingredient equally, the retailer's own label
SHALL be preferred, unless the recipe named a brand.

#### Scenario: Two products of the same kind

- **WHEN** an own-label product and another brand are both the right kind of thing
- **THEN** the own label is preferred, being usually the cheaper of the two

#### Scenario: An own-label product of the wrong kind

- **WHEN** an own-label product is not the kind of thing the ingredient asks for
- **THEN** it is not preferred over a correctly matched product from another brand

#### Scenario: The recipe named a brand

- **WHEN** an ingredient names a particular brand
- **THEN** that is honoured rather than overridden by the own label
