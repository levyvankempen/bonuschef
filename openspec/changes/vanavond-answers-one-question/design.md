## Context

See proposal.md. The facts, measured on live production data for one shop:

| | |
|---|---|
| recipes in the pool | 944 |
| ranked (cheaper today) | 40 |
| **ranked with exactly one discounted ingredient** | **40** |
| ranked with two or more | 0 |
| distinct ingredients driving all 40 | 19 |
| top 20 | zalm 11, sinaasappel 3, spek 5, other 1 |
| concepts whose label contains "spek", one shop | **8** |

Re-sorting was tested and is not the answer. Distinct ingredients in the top ten:
`saving_total DESC` 4, `saving_pct DESC` 6, `cost_today_per_serving ASC` 6. Zalm
dominates regardless, because 11 of 40 ranked recipes contain it. One-per-driving-
ingredient yields 12 distinct in 12 slots.

## Goals / Non-Goals

**Goals:**

- Six cards carry six decisions.
- The number on the card can be checked against the sticker.
- "I don't eat this" is sayable where it is felt and reversible where it is
  reviewed.
- A shopper's page contains no control that changes other people's data.

**Non-Goals:**

- Not `saving_per_serving` in the mart. Deferred: a dbt build and a change to
  every rank, for a problem that choosing for difference mostly removes.
- Not two strengths of exclusion. See below.
- Not restyling the card. `render_recipe_card` is one shared renderer, its
  image-measurement problem is solved and documented, and its fragment
  discipline was hard-won. This changes what the page selects and who it talks
  to, not how a card looks.
- Not scoping adopted recipes per account. A real defect, flagged, needs its own
  decision.

## Decisions

### Soft dedup with a fill-up pass, not one-per-ingredient

Hard one-per-ingredient fails at both ends: 19 driving ingredients means a
19-card page with no lead, and 2 means two cards while 38 recipes are cheaper.

So: walk the ranking in order, take the first recipe for each ingredient not yet
represented, and if fewer than the page wants remain, fill from the largest
groups in rank order. The lead card is unchanged - still the best overall - so
"there is a clear best option" keeps holding.

The drill-down sets the **existing** pill rather than adding a control. The page
already has one ingredient affordance; a second would mean two ways to ask one
question, which is how the free-text box and the pills came to overlap.

### The exclusion is keyed on concept, and says what it hides

`concept_id` is what resolutions, the matcher and the review flow are keyed on,
and what `fct_recipe_opportunity_items` carries. `item_label` is the recipe's own
word: the measured data has `biologische spekreepjes`, `biologische gerookte
spekreepjes` and `magere spekblokjes` as three labels.

But one food answers to many names - **eight concepts match "spek" in one shop** -
so a single concept block is narrower than "no bacon" and would feel broken on
first use. Blocking by text would be broad enough and would also hide
`plantaardige spekreepjes`, which someone avoiding pork may well want.

Resolution: block concepts, but when one is chosen, offer its siblings by name
and let the person take them in one go. The bluntness becomes visible and chosen
rather than silent in either direction.

### One strength of exclusion, not two

There is a real difference between "I don't eat this" and "stop pushing it at
me". Two strengths on a phone is a radio button inside a popover, and nobody
reads it.

So one control with hard semantics, and the weaker case is served by shipping
dedup in the same change: after it, bacon is one card of six rather than five,
which is what "stop pushing it at me" means. The exclusion is then reserved for
genuine dislikes.

### Applied at read time, in the portal

`int_pool_recipes_available` already argues this: adding an account dimension to
the 2,000-row spine of the ranking multiplies it per account, where filtering a
few hundred rows at read time is cheap. The same note is why dismissal moved to
the portal - and why it then went missing for months, which is the cautionary
half of the precedent.

Uncached, like the dismissal filter, because it changes the moment the button is
pressed.

### Exclusion is membership; dedup is presentation

They must stay at different stages or neither is explainable:

- the exclusion decides which recipes are candidates, before ranking is consulted
- dedup decides which candidates get the card slots, after

Implementing dedup as "down-rank what you dislike" merges them into one fuzzy
score. This page's whole character is that every figure traces to a sentence -
`minstens`, `±`, `Schatting over 5 van 9` - and a blended relevance score has no
sentence.

### The console moves rather than being deleted

Taking diagnostics off Vanavond only works if the operator can still see them, so
they go to Beheer: pipeline health detail, flagged concepts, the unresolved count
and the way into the review.

The **credential failure stays** on Vanavond. The existing requirement argues
that page is "the only surface on which a failure can be noticed", and a dead
credential means the prices shown may be wrong - which is a shopper's business.
The code already separates it out.

### The operator gate goes in the function, not only the page

`confirm_resolution` is gated itself, not merely hidden. A dialog that is not
offered is still reachable, and this one writes a table with no account column:
the blast radius is every account's prices. Hiding a control is presentation;
refusing the write is the wall.

## Risks / Trade-offs

- **Dedup can show a worse recipe than the one it suppressed.** Deliberate: the
  second-best bacon recipe is worth less than the best salmon one, because the
  page's job is to present choices rather than a sorted list.
- **Concept-level exclusion will feel narrow until the sibling offer works
  well.** It is the part most likely to need a second pass after real use.
- **Moving the console is a behaviour change for the operator**, who will look
  for those numbers where they used to be. The documented path should say they
  moved.
- **The coverage caption gets wordier.** The honesty requirement leaves no
  choice: a count of what was computed, beside a shortlist, misrepresents the
  selection.
