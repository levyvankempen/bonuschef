WITH

int_recipe_items_priced AS (
    SELECT * FROM {{ ref('int_recipe_items_priced') }}
),

dim_recipe AS (
    SELECT * FROM {{ ref('dim_recipe') }}
),

agg AS (
    SELECT
        t1.recipe_id,
        -- NULL when any ingredient is unpriced. SUM skips NULLs, so without
        -- this guard a recipe missing its rookworst publishes a confident
        -- total that is simply too low - and this is the figure the portal
        -- shows. fct_recipe_cost_history has always done this; this mart did
        -- not, and an unresolved ingredient makes it wrong immediately.
        CASE
            WHEN COUNT(t1.price) = COUNT(*)
                THEN ROUND(SUM(t1.item_cost)::numeric, 2)
        END AS total_cost,
        ROUND(SUM(t1.item_cost)::numeric, 2) AS partial_cost_observed,
        COUNT(*) AS items_total,
        COUNT(t1.price) AS items_priced,
        COUNT(*) FILTER (WHERE t1.is_unresolved) AS items_unresolved,
        COUNT(t1.price)::numeric / NULLIF(COUNT(*), 0) AS price_coverage
    FROM int_recipe_items_priced AS t1
    GROUP BY t1.recipe_id
)

SELECT
    d.recipe_id,
    d.recipe_name,
    d.servings,
    a.total_cost,
    a.partial_cost_observed,
    COALESCE(a.items_total, 0) AS items_total,
    COALESCE(a.items_priced, 0) AS items_priced,
    COALESCE(a.items_unresolved, 0) AS items_unresolved,
    COALESCE(a.price_coverage, 0) AS price_coverage,
    ROUND((a.total_cost / NULLIF(d.servings, 0))::numeric, 2)
        AS cost_per_serving
-- LEFT, not INNER. A recipe whose ingredients all fail to price used to
-- disappear from this mart entirely, so the portal showed nothing rather than
-- an unknown cost - a silent drop that looked like the recipe was deleted.
FROM dim_recipe AS d
LEFT JOIN agg AS a
    ON d.recipe_id = a.recipe_id
