# An ingredient resolves to the right kind of thing

## Why

"verse dille" resolves to Verstegen Dille — dried dill in a glass jar, in the
spice aisle. It is the wrong product, and nothing in the system can tell,
because resolution compares names and nothing else.

Two mechanisms propose products, and both fail this way for the same reason.

The local matcher requires the ingredient name to appear as a whole phrase in
a product name. "wortel" appears in "AH Vormservet wortel", a carrot-printed
paper napkin, so a napkin resolves an ingredient. The AH product search that
handles what the matcher cannot is relevance-ranked; its own docstring in this
repository already records that it is *"wrong on roughly one in five —
confidently so"*.

A live audit of 368 currently-linked products found three resolving to Non
Food. They are worth naming, because each is a confident wrong answer that no
amount of name comparison could catch:

    wortel                  -> AH Vormservet wortel   (a paper napkin)
    kropje babyromainesla   -> Bisolvon siroop        (cough medicine)
    runderbouillon van tab  -> Aleve Feminax          (menstrual painkillers)

The retailer already publishes what these products *are*. Every product
carries a taxonomy path and a store department:

    AH Dille         Vers       Groente, aardappelen > Verse kruiden, gember, pepers > Verse kruiden
    Verstegen Dille  Houdbaar   Soepen, sauzen, kruiden > Kruiden, specerijen > Gedroogde kruiden > Dille

The same distinction the eye makes instantly is already in the data. We have
never fetched it.

## What Changes

Resolution starts comparing kinds, not only names.

- Products carry the retailer's taxonomy and store department.
- A candidate whose kind contradicts the ingredient is not proposed — a
  non-food product never resolves a food ingredient, and an ingredient asking
  for something fresh is not satisfied from the dried-goods aisle.
- Where the taxonomy names the ingredient exactly, that candidate is
  preferred over one that merely mentions it in its title.
- Existing resolutions are re-checked against their taxonomy, so the wrong
  ones already in the database surface instead of persisting silently.
- A person reviewing a match sees what kind of thing each candidate is.

## Impact

- Affected specs: `recipe-catalogue`
- Affected code: `utils/ah_recipes.py`, `dags/defs/assets/resolution/`,
  `portal/matching.py`, `portal/db.py`, `portal/review.py`, a new staging
  model and a new source table

## Out of scope

- Re-resolving every concept from scratch. Confirmed human decisions stay
  authoritative, and this change must not quietly overwrite them.
- Folding synonymous concepts together. `ah_ingredient_aliases` exists and is
  unused; taxonomy would be a good basis for it, and it is a separate change.
