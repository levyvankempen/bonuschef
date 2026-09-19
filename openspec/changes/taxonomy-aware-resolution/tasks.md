# Tasks

## 1. Fetch what a product is

- [x] 1.1 Add `taxonomies { id name }` and `properties { code values }` to the
      product search query; extend `ProductHit`
- [x] 1.2 Add a `fetch_product_taxonomy()` using alias-batched `product(id:)`
- [x] 1.3 Tests: parsing, a product with no taxonomy, a missing department

## 2. Store it — NOT DONE, and deliberately

Classification is fetched per run rather than cached. Alias batching makes the
whole catalogue about 38 requests, which is cheap enough that a cache would be
the more expensive thing: a stored classification goes stale silently when AH
reclassifies a product, and the failure mode is a wrong rejection nobody can
see. Revisit if the request count becomes a problem.

- [x] 2.1 Decided against; recorded here rather than left looking unfinished

## 3. Apply it when proposing

- [x] 3.1 A `classification` module: non-food rejection, form agreement,
      leaf preference — pure functions, no network, no database
- [x] 3.2 Wire it into `_propose_from_ah` and the local matcher's output
- [x] 3.3 Tests: the dill case, the napkin case, abstention when the
      ingredient states no form, and that preference never rejects

## 4. Re-check what is already recorded

- [x] 4.1 Classify linked products and flag contradictions
- [x] 4.2 Never touch `confirmed_at IS NOT NULL`
- [x] 4.3 Flagged concepts enter the review queue. The queue's predicate was
      reworked: "never looked at, OR looked at and since found to contradict
      itself". Flagged first, because a wrong price is costlier than a gap
- [x] 4.4 Tests, including that a confirmed row survives a contradiction

## 5. Show it — NOT DONE

- [x] 5.1 The dialog says why a flagged concept came back
- [ ] 5.2 Candidate rows show their classification — still open


## 6. Rank and narrow (added after the first round)

- [x] 6.1 A score over explainable signals: leaf naming, leaf consensus,
      head-noun position, genericness, retailer order as tiebreak
- [x] 6.2 Dutch plural handling, because "sjalot"/"sjalotten" and
      "kaas"/"kazen" are the common case and a prefix match resolved flour
      as cauliflower rice
- [x] 6.3 Propose only the cohort sharing the best candidate's kind
- [x] 6.4 Measured against the 84 human-confirmed links rather than asserted
- [x] 6.5 A confidence floor was tried, measured, and removed - the scores do
      not separate confirmed from unconfirmed-but-correct
