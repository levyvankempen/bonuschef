"""The pool of well-regarded Allerhande recipes.

Unlike the clearance source next door, this is **not** append-only. Clearance is
append-only because the markdown curve *is* the data — the same item's discount
deepens through the day and that history cannot be re-fetched. A recipe is a
slowly-changing dimension: 0.77% of the catalogue changed in the last 30 days.
So this merges on ``recipe_id`` and the pool is refetched whole rather than
accumulated.

Bounded by AH's own ordering. ``recipeSearch`` refuses ``start + size > 2000``,
and here that ceiling is the feature rather than the obstacle: the top 2,000 by
rating is exactly the pool worth holding, and it costs about 37 requests a week
against a measured tolerance of several hundred a day. Holding all 24,803
recipes is affordable and still wrong — it makes the ingredient review queue
unboundedly long and turns a personal tool into a mirror of someone else's
catalogue.
"""

from datetime import datetime, timezone

import dlt
from dagster import AssetExecutionContext, RetryPolicy, asset

from bonuschef.utils.ah_recipes import (
    AHRecipeUnavailable,
    enumerate_pool,
    fetch_recipes,
)

# What a refresh may spend before it is a bug rather than a job. A full refresh
# is ~37 requests; this is an order of magnitude of headroom and still far under
# what AH tolerates. Its purpose is to stop a loop, not to ration.
MAX_REQUESTS_PER_REFRESH = 500


@dlt.source(name="ah_recipe_pool")
def recipe_pool_source(recipes, fetched_at: str):
    """Two resources from one fetch, so both describe the same pool."""

    def _recipes():
        for r in recipes:
            yield {
                "recipe_id": r.recipe_id,
                "title": r.title,
                "servings": r.servings,
                "url": r.url,
                "image_url": r.image_url,
                "description": r.description,
                "cook_time_min": r.cook_time_min,
                "rating_average": r.rating_average,
                # Stored beside the average and never without it: five stars
                # from three votes is not the claim five stars from three
                # hundred is, and the portal has to be able to say so.
                "rating_count": r.rating_count,
                "modified_at": r.modified_at,
                "fetched_at": fetched_at,
            }

    def _ingredients():
        for r in recipes:
            for line_no, ing in enumerate(r.ingredients):
                yield {
                    "recipe_id": r.recipe_id,
                    "line_no": line_no,
                    "concept_id": ing.concept_id,
                    "concept_name": ing.name,
                    "quantity": ing.quantity,
                    "unit": ing.unit,
                    "raw_text": ing.raw_text,
                    "fetched_at": fetched_at,
                }

    return (
        # replace, not merge. merge upserts and never deletes, so a recipe that
        # fell out of AH's listing stayed in the pool and kept being ranked -
        # the opposite of this module's own docstring and of the requirement
        # that the pool is refreshed rather than accumulated.
        #
        # Safe because the asset refuses to write when it has no recipes, so a
        # failed fetch cannot truncate a good pool. A *partial* fetch does
        # shrink it, deliberately: the portal shows the pool size, so a collapse
        # reads as a number that dropped rather than as a ranking quietly drawn
        # from months of stale recipes.
        dlt.resource(
            _recipes,
            name="ah__pool_recipes",
            write_disposition="replace",
            primary_key="recipe_id",
        ),
        dlt.resource(
            _ingredients,
            name="ah__pool_recipe_ingredients",
            write_disposition="replace",
            primary_key=["recipe_id", "line_no"],
        ),
    )


@asset(
    name="ah__recipe_pool",
    # group_name="dlt" is load-bearing, not cosmetic. daily_refresh_job selects
    # `AssetSelection.all() - AssetSelection.groups("dlt")`, so an asset outside
    # this group would refetch the entire pool every night at 17:30, inside the
    # dbt rebuild and against the only concurrency slot.
    group_name="dlt",
    # One retry, not two. A refresh is never urgent and the credential is the
    # scarce thing; retrying a rejected credential is how it gets burned.
    retry_policy=RetryPolicy(max_retries=1, delay=120),
)
def ah__recipe_pool_asset(context: AssetExecutionContext) -> None:
    """Refresh the pool of well-regarded recipes."""
    try:
        hits = enumerate_pool()
    except AHRecipeUnavailable as exc:
        # Abort rather than retry-loop. The auth layer has already tried one
        # forced refresh; going round again through the fallback chain is
        # precisely how a refresh credential dies.
        raise RuntimeError(
            f"Recipe pool refresh aborted: {exc}. Clearance collection and the "
            "credential heartbeat are unaffected; re-run this job by hand once "
            "the cause is understood."
        ) from exc

    context.log.info("Enumerated %d curated main courses", len(hits))

    recipes, failed = fetch_recipes([h.recipe_id for h in hits])
    if failed:
        # Named, not swallowed: a recipe AH will not serve is a recipe that
        # silently leaves the pool, and that should be visible in the run log.
        context.log.warning(
            "%d of %d recipes could not be fetched or parsed: %s",
            len(failed),
            len(hits),
            failed[:20],
        )
    if not recipes:
        raise RuntimeError(
            "Recipe pool refresh returned no usable recipes; refusing to write "
            "an empty pool over a good one."
        )

    fetched_at = datetime.now(timezone.utc).isoformat()
    pipeline = dlt.pipeline(
        pipeline_name="ah_recipe_pool_pipeline",
        destination="postgres",
        dataset_name="public",
        progress="log",
    )
    load_info = pipeline.run(recipe_pool_source(recipes, fetched_at))
    context.log.info(
        "Loaded %d recipes (%d ingredient lines): %s",
        len(recipes),
        sum(len(r.ingredients) for r in recipes),
        load_info,
    )
    context.add_output_metadata(
        {
            "recipes": len(recipes),
            "ingredient_lines": sum(len(r.ingredients) for r in recipes),
            "unfetchable": len(failed),
            "rated": sum(1 for r in recipes if r.rating_average is not None),
        }
    )
