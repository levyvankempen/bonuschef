## Why

The portal is used standing in an Albert Heijn, phone in one hand, basket in the
other. Every recipe it shows is a paragraph with a 56-96 pixel thumbnail beside
it - a coloured square, not a dish. The figure the whole application exists to
produce, the saving, is rendered as bold body text while the total price above it
is a heading, so the page reads name first, price second, saving last. That is
the reverse of the order the decision is made in.

Nothing on a card says *why* a recipe is cheap. The badges count offers
("2x bonus") where the person needs the noun: the kipfilet is what is discounted,
and the kipfilet is what they are standing in front of. The data to say so is
already published and already ordered by saving; the card simply does not read it.

And there is no way in to the catalogue from an ingredient. A person looking at
discounted chicken cannot ask what to cook with it. The only search is a
substring over the names of *saved* recipes, which cannot answer it in principle,
and which crashes on a search term containing `(`, `+` or `*` because the
substring test is a regular expression.

## What Changes

- Recipe recommendations become **cards led by their image**, at the largest size
  the source actually provides, with the saving as the largest element and the
  discounted ingredients **named** on the card.
- Recipe images are upgraded from AH's 220x162 variant to its 440x324 variant by
  rewriting the stored URL. AH publishes exactly these two sizes and nothing
  larger, so 440 is also the ceiling: the card SHALL NOT upscale past it.
- A person can **start from an ingredient**: a search field on the page that
  answers "what shall I cook", plus one tap on the ingredients that are
  discounted today, which is the in-store case and requires no typing.
- A search term is treated as text rather than as a pattern, fixing a live crash.
- Deleting a saved recipe is confirmed, because it is permanent, unguarded, and
  sits beside a routine button on a phone.
- A collapsed ingredient list stops querying and stops registering its controls
  while collapsed - presently a single render of the tonight page issues up to
  six extra queries and registers ~54 buttons nobody asked to see.
- Pipeline health and coverage commentary move below the answer, which the portal
  spec already requires and the tonight page does not presently honour.

Deliberately **not** in this change, and why: a tickable shopping list (the
largest new capability here and worth its own change); putting page state in the
URL so a dropped websocket survives a reload; cook time on the card, which needs
two dbt models to carry a column they presently drop; and the clearance page's
own filter and pagination work.

## Capabilities

### New Capabilities

None. Every behaviour here belongs to the existing `portal` capability.

### Modified Capabilities

- `portal`: recommendations are presented as image-led cards that name the
  discounted ingredient driving the saving; imagery is shown at the source's
  usable resolution and never upscaled beyond it; a person can find a recipe by
  ingredient, including without typing; a search term is data rather than a
  pattern; destroying a saved recipe is confirmed; and a collapsed detail costs
  nothing to render.

## Impact

- `src/bonuschef/portal/tonight_page.py` - card renderers, ingredient search,
  demotion of pipeline chrome, collapsed-detail cost.
- `src/bonuschef/portal/recipes_page.py` - card renderer, the regex search bug,
  the unguarded delete.
- `src/bonuschef/portal/ui.py` - a shared card renderer and the image-variant
  rewrite, so the two pages cannot drift.
- `src/bonuschef/portal/db.py` - one new cached reader for recipes matching an
  ingredient, and the discounted-ingredient list for the tap targets.
- No mart, model or pipeline change. The image upgrade is a URL rewrite, so all
  908 pool recipes gain it without a backfill or a re-fetch.
