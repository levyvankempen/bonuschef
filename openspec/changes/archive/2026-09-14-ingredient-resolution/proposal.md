## Why

Adopting a recipe now works, and the first real one landed with **4 of its 9 ingredients matched**. The other five — *milde olijfolie*, *friszoete appel*, *plantenmargarine lactosevrij*, *bloem*, *bospaddenstoelenfond* — are visibly unresolved and the recipe's cost is honestly withheld. That honesty is worth having, but a recipe that says `€10.26+` forever is not the point of the project.

The matcher is deliberately crude: it takes products whose name contains the ingredient as a whole word and refuses anything compound. That refuses *"Bonduelle pasta pronto fusilli courgette broccoli"* correctly, and it also refuses *milde olijfolie* because the catalogue spells it *"AH Olijfolie mild"*. Word order, a missing adjective, a brand in front — the misses are ordinary and a person can resolve each of them in seconds. There is simply no way to tell the system.

The unmet half of the previous change is exactly this: proposals persist and are reused, but nobody can confirm or correct one. The resolution table can only be edited with SQL.

This is also where the leverage is. Concepts are shared — one sampled set of 150 recipes used only 473 distinct ingredients, and *milde olijfolie* appeared in 104 of them. Resolving an ingredient once serves every recipe that will ever use it, so the work per recipe falls sharply as the collection grows. That is what turns twenty recipes from a chore into a list.

## What Changes

- An ingredient's resolution can be reviewed and corrected by a person, in one place, with the automatic proposals already selected so agreeing costs nothing.
- A correction is durable: re-running the matcher can fill a gap but SHALL never overwrite a decision someone made.
- A person can record that an ingredient has no purchasable equivalent, distinctly from nobody having looked at it yet — "there is no product for *bospaddenstoelenfond*" is an answer, and the system currently cannot hold it.
- Where an ingredient resolves to several products, the cheapest available is what a recipe costs, since which is cheapest changes daily and that is the whole premise.
- Correcting is reachable from wherever the gap is visible, so noticing and fixing are the same act.

Deliberately **not** here: unit conversion. A recipe asking for 300 g of something sold in 500 g packs still costs one pack, as it does today, and the page still says so.

## Capabilities

### New Capabilities
<!-- None. -->

### Modified Capabilities
- `recipe-catalogue`: adds the human half of resolution — confirming, correcting, and recording that nothing satisfies an ingredient — alongside the automatic proposing that already exists.
- `portal`: adds requirements for reviewing resolutions without turning adoption back into a per-ingredient chore.

## Impact

- `src/bonuschef/portal/` — a review surface, reachable from the recipe view and from the post-adoption card.
- `src/bonuschef/portal/db.py` — reading unresolved concepts, writing confirmations, recording an ingredient as having no product.
- `public.ah_ingredient_products` gains a decision state; `public.ah_ingredient_review` is new.
- The recipe cost models already take the cheapest attached product and already withhold a partial total; this change fills the table they read rather than altering them.
- No change to adoption, which must stay a search, a look and a button.
