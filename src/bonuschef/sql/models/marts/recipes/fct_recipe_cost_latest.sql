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
        ROUND(SUM(t1.item_cost)::numeric, 2) AS total_cost
    FROM int_recipe_items_priced AS t1
    GROUP BY t1.recipe_id
)

SELECT
    d.recipe_id,
    d.recipe_name,
    d.servings,
    a.total_cost,
    ROUND((a.total_cost / NULLIF(d.servings, 0))::numeric, 2)
        AS cost_per_serving
FROM agg AS a
INNER JOIN dim_recipe AS d
    ON a.recipe_id = d.recipe_id
