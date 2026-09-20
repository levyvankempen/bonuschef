# Design

## Where the signal comes from

`searchProducts` and `product(id:)` both return, per product:

```
taxonomies { id name }        Groente, aardappelen > Verse kruiden, gember, pepers > Verse kruiden
properties { code values }    da_store_department: ["Vers"]
```

`da_store_department` has five values across the catalogue — measured, not
assumed: `Vers` (219 of a 240-product sample), `Houdbaar` (171), `Non Food`
(119), `Diepvries` (61), `Near Food`. It is coarse, which is exactly why it is
safe to act on: it separates a napkin from a carrot without pretending to
know whether one carrot is better than another.

`product(id:)` matters as much as the search. It takes alias batching the way
`recipe(id:)` does, so the 1,901 products already linked can be classified
without a search per concept.

## Which check does what

Three checks, in increasing order of how much they claim to know.

**Non-food rejection.** A food ingredient is not satisfied by a `Non Food`
product. This is the cheapest and most certain check. It is also the lowest
yield: the audit found 3 such links in 368. Worth doing because the failures
it catches are absurd, not because they are common.

**Form agreement.** If the ingredient says "verse" or "koelverse", require
`Vers`; if it says "gedroogde", require `Houdbaar`. This is the dill case, and
the only check that reads the ingredient's own words.

It abstains when the ingredient says nothing about form, which is the common
case. That asymmetry is deliberate — "dille" unqualified should still match
either, because a recipe that does not specify has not expressed a preference.

**Taxonomy-leaf preference.** When a candidate's leaf taxonomy name equals the
ingredient name, prefer it. This turned out to be the strongest signal, and
the surprise of the investigation: AH's leaves are named the way recipes name
ingredients.

    witte kaas      -> leaf "Witte kaas"
    gerookte zalm   -> leaf "Gerookte zalm"
    slagroom        -> leaf "Slagroom"
    bladpeterselie  -> leaf "Verse kruiden"   (no exact leaf; preference abstains)

It only ever reorders. It never rejects, because a missing leaf match means
the taxonomy is coarser than the ingredient, not that the candidate is wrong.

## Where it lives

Not in `matching.py`. A test asserts that module imports no network code, and
that test is right: the local matcher is the offline path, and it must stay
runnable without a token.

Classification is fetched in `ah_recipes.py` alongside the existing product
search, stored, and applied in the resolution asset. The matcher keeps
proposing on names; the asset filters on kinds. That also means the filter
covers both proposal sources with one implementation, rather than each
matcher growing its own copy.

## Storage

A new portal-owned table `ah_product_taxonomy`, keyed by `webshop_id`:

| column | |
|---|---|
| `webshop_id` | joins to `int_product_crosswalk`, which already derives it from `product_link` |
| `department` | the `da_store_department` value |
| `taxonomy_path` | the full `>`-joined path, for display |
| `taxonomy_leaf` | the last segment, which is what the preference compares |
| `fetched_at` | |

Keyed by product, not by `(concept, product)`: what a product *is* does not
depend on which ingredient is considering it, and storing it per pair would
refetch the same classification once per concept that shares a product.

Nothing is added to `ah_ingredient_products`. Its grain is a decision about a
pair; taxonomy is a fact about a product, and putting a fact in a decision
table is how the two start disagreeing.

## Re-checking what is already recorded

The wrong answers are already in the database, so a check that only guards new
proposals would fix almost nothing.

A re-check pass classifies linked products and acts on contradictions, under
two conditions that together make it safe:

- `confirmed_at IS NOT NULL` is never touched. A human decision outranks any
  rule here.
- A contradicting proposal is withdrawn **only if the concept keeps at least
  one acceptable proposal**. Otherwise it is left in place and the concept is
  raised for review instead.

The second condition is the important one. Deleting the last candidate turns a
visibly wrong price into a silently missing one, and silence is the failure
mode this project consistently treats as worse — a wrong product on the page
is something a person can see and correct, an absent one is not.

So "mierikswortel in pot", currently resolved to pesto, salsa and peanut
butter, loses them if a real horseradish is among its candidates, and keeps
them with a flag if it is not.

## What this does not fix

Resolution still cannot tell a good carrot from a bad one, and nothing here
helps with "sjalot" returning a Boursin — Boursin is `Vers`, cheese is food,
and no taxonomy rule rejects it. The leaf preference will rank an actual
shallot above it when one exists, which is the most this change claims.
