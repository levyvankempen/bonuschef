"""Propose products for the pool's unresolved ingredient concepts.

The pool is useless without this. Fetching 900 recipes is cheap and fast; what
makes them *rankable* is knowing which product an ingredient can be bought as,
and until that exists a 900-recipe pool prices 3.3% of its ingredients and ranks
nothing at all.

The matcher runs entirely against the local catalogue - no network, no AH
credential - so this costs nothing but CPU and can be re-run freely.

**These are proposals, not confirmations.** ``propose_products`` writes with
``confirmed_at`` NULL and refuses to overwrite anything a person has decided, so
re-running after a catalogue refresh can never revert a correction. The portal's
review queue is where a proposal becomes a decision; this job only ensures there
is something to review, ordered by how much difference it makes.
"""

from dagster import AssetExecutionContext, AssetKey, RetryPolicy, asset
from sqlalchemy import text

from bonuschef.portal.db import get_engine, propose_products
from bonuschef.portal.matching import propose_for

# Most-used concepts first. Concept frequency is steep - a few hundred cover
# most ingredient lines - so if this is ever interrupted, the work that has
# landed is the work that mattered.
_UNRESOLVED_CONCEPTS = """
    SELECT i.concept_id, MIN(i.concept_name) AS concept_name, COUNT(*) AS uses
    FROM public."ah__pool_recipe_ingredients" AS i
    LEFT JOIN public.ah_ingredient_products AS p
        ON i.concept_id = p.concept_id
    WHERE p.concept_id IS NULL
    GROUP BY i.concept_id
    ORDER BY uses DESC, i.concept_id ASC
"""


@asset(
    name="ah__ingredient_proposals",
    # Not group_name="dlt": that group is excluded from the nightly rebuild
    # because those assets spend the AH credential. This one spends nothing and
    # should run whenever the catalogue moves, since a product that appeared
    # today may resolve an ingredient that failed to match yesterday.
    group_name="resolution",
    retry_policy=RetryPolicy(max_retries=1, delay=30),
    # dim_product keys as a path because dbt models are grouped by folder.
    deps=[AssetKey("ah__recipe_pool"), AssetKey(["marts", "dim_product"])],
)
def ah__ingredient_proposals_asset(context: AssetExecutionContext) -> None:
    """Match unresolved pool concepts against the product catalogue."""
    engine = get_engine()

    with engine.begin() as conn:
        rows = conn.execute(text(_UNRESOLVED_CONCEPTS)).mappings().all()
    concepts = {int(r["concept_id"]): r["concept_name"] for r in rows}
    if not concepts:
        context.log.info("Every pool concept already has a product; nothing to do.")
        context.add_output_metadata({"unresolved": 0, "proposed": 0})
        return

    context.log.info("Matching %d unresolved concepts", len(concepts))
    proposals = propose_for(engine, concepts)
    propose_products(engine, proposals)

    resolved = len({p["concept_id"] for p in proposals})
    context.log.info(
        "Proposed %d products across %d of %d concepts",
        len(proposals),
        resolved,
        len(concepts),
    )
    context.add_output_metadata(
        {
            "unresolved_before": len(concepts),
            "concepts_matched": resolved,
            "products_proposed": len(proposals),
            # The ones a person still has to decide. This is the review queue,
            # and it is the honest measure of how far off a full answer is.
            "still_unmatched": len(concepts) - resolved,
        }
    )
