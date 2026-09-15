-- The strongest test in the set.
--
-- The opportunity mart's "ordinary" must be the same basket that
-- fct_recipe_cost_latest totals. Any divergence means the candidate set or the
-- valid_to filter has drifted, or the concept fan-out is double-counting - and
-- the portal would show two different answers to "what does this cost".

SELECT
    o.store_id,
    o.recipe_id,
    o.cost_ordinary,
    l.total_cost,
    o.items_total,
    l.items_total AS cost_items_total
FROM {{ ref('fct_recipe_opportunity') }} AS o
INNER JOIN {{ ref('fct_recipe_cost_latest') }} AS l
    ON o.recipe_id = l.recipe_id
WHERE o.cost_ordinary IS DISTINCT FROM l.total_cost
    OR o.items_total <> l.items_total
