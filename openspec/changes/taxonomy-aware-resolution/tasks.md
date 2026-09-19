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
- [ ] 4.3 Flagged concepts enter the review queue — NOT DONE. They are
      reported in the asset's output metadata and logged; wiring them into the
      portal's queue needs the queue's "has a person looked" predicate
      reworked, which is its own change
- [x] 4.4 Tests, including that a confirmed row survives a contradiction

## 5. Show it — NOT DONE

- [ ] 5.1 Candidate rows in the review dialog show their classification
- [ ] 5.2 Test
