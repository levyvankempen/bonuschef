WITH

items AS (
    SELECT * FROM {{ ref('int_recipe_items_priced') }}
),

recipe_totals AS (
    SELECT
        recipe_id,
        SUM(item_cost) AS total_cost
    FROM items
    GROUP BY recipe_id
)

SELECT
    d.recipe_id,
    d.recipe_name,
    i.product_name,
    i.product_link,
    i.quantity,
    i.price,
    ROUND(i.item_cost::numeric, 2) AS item_cost,
    ROUND((i.item_cost / NULLIF(rt.total_cost, 0) * 100)::numeric, 1) AS cost_pct
FROM items AS i
INNER JOIN recipe_totals AS rt ON i.recipe_id = rt.recipe_id
INNER JOIN {{ ref('dim_recipe') }} AS d ON i.recipe_id = d.recipe_id
