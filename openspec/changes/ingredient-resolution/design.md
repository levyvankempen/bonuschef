## Context

See `proposal.md` — Why. The state this builds on, measured on the first real adoption:

- `Zuurkoolstamppot met vegan kipbraadworst`: 9 ingredients, **4 matched**, `total_cost` NULL, `partial_cost_observed` 10.26, coverage 0.44.
- The five misses are ordinary vocabulary problems, not exotic ones: *milde olijfolie* against a catalogue entry reading *"AH Olijfolie mild"*, *friszoete appel*, *bloem*, *plantenmargarine lactosevrij*, *bospaddenstoelenfond*.
- `public.ah_ingredient_products` already holds `(concept_id, product_link)` with a `confirmed_at` that nothing yet sets, and `propose_products` already refuses to overwrite a row where `confirmed_at IS NOT NULL`.
- `int_recipe_items_priced` already picks the cheapest priced candidate per ingredient and already keeps a placeholder row when there are none. The cost side of this change is therefore mostly already built; what is missing is a way to put rows in the table.

## Goals / Non-Goals

**Goals:**

- Let a person settle an ingredient in seconds, once, for every recipe that will ever use it.
- Make a human decision durable against every future run of the matcher.
- Keep adoption exactly as it is: a search, a look, and a button.

**Non-Goals:**

- Unit conversion. Still deferred, still stated on the page.
- Improving the matcher. Better proposals would reduce the work, but the work cannot currently be done at all, and a better matcher with no correction path is still a dead end.
- A separate ingredients section in the navigation. One person with a few hundred concepts does not need a fourth destination.

## Decisions

**Three decision states, not two.**
`confirmed_at` alone cannot express "a person looked and there is no such product". Without that state, *bospaddenstoelenfond* stays on the outstanding list forever and the list stops being a list of work. A separate `ah_ingredient_review` table records `resolved` or `none_exists` per concept, so "nobody has looked" is the absence of a row rather than an overloaded NULL.

**Confirmation is a dialog over all outstanding ingredients at once, not a step per ingredient.**
The entire reason the previous flow failed was nine interactions per ingredient. A modal listing every unresolved concept with its proposals pre-selected, settled by one button, keeps the cost proportional to *how many ingredients are genuinely uncertain* rather than to how many ingredients exist. Adoption does not open it; it offers it.

**Multi-select over pills, and an empty selection is a valid answer.**
An ingredient legitimately resolves to several products — that is the premise of costing the cheapest — so the control has to be multi-select. And choosing nothing must submit rather than fail validation, because "nothing satisfies this" is the answer the `none_exists` state exists to record.

**A decision beats a proposal, enforced in SQL rather than in the UI.**
`propose_products` already carries `WHERE p.confirmed_at IS NULL` on its upsert. Confirmation sets `confirmed_at`, and deselecting deletes the row. The guarantee therefore lives in the statement, not in a code path someone can forget to call — which matters because the matcher runs on every adoption, unattended.

**Correction is reachable from the recipe view, not only from a review queue.**
Noticing a wrong product and fixing it should be one act. The same dialog opens scoped to a single concept, and because resolution lives on the concept rather than on the recipe, fixing it once fixes every recipe using it — which is the spec's requirement obtained by construction rather than by a fan-out update.

**Rebuilding after a correction is fire-and-forget, as adoption is.**
Blocking the dialog on a Dagster run would make settling five ingredients a five-minute wait; runs are serialised instance-wide, so they would queue behind each other. The cost updates shortly afterwards, and a recipe whose cost has not caught up is honest in the meantime because an unpriced basket already withholds its total.

## Risks / Trade-offs

- **A person can confirm a wrong product, and it will stick.** That is the point — their decision beats the matcher — but it means a mistake persists until noticed. → Mitigated by the correction path being available wherever the resolution is visible, and by the decision being distinguishable from a proposal so a wrong one can be found.
- **`none_exists` can be wrong too**, and an ingredient wrongly marked as unpurchasable silently keeps a recipe incomplete forever. → It is recorded per concept and shown on the recipe as a distinct state rather than as an ordinary gap, so it reads as a decision rather than as an oversight.
- **The dialog can still be long** for someone adopting a first recipe with nine unknown ingredients. → Unavoidable at the start and self-limiting by design: concepts are heavily shared, so the list shortens with every recipe. That is the amortisation the whole approach rests on.
- **Deleting a deselected row loses the fact that it was ever proposed.** → Acceptable: the matcher can propose it again, and keeping rejected rows would need a fourth state to stop them being re-proposed endlessly.

## Migration Plan

1. Land the repo changes; the CI session set is the gate.
2. The new table is created by the portal's existing startup path; no migration of existing rows is needed, because an unconfirmed proposal is exactly what the new state calls "not yet decided".
3. Rollback is `git revert` plus a rebuild. Confirmed rows would remain and simply stop being distinguishable from proposals.
