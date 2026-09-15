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
    i.item_key,
    -- What the recipe asked for, kept beside what we would buy. The portal fell
    -- back to product_name without it, so an adopted recipe's "aardappel" was
    -- displayed as "AH Aardappels" and an unresolved line had nothing to show.
    i.item_label,
    i.product_name,
    i.product_link,
    i.is_unresolved,
    i.quantity,
    i.price,
    ROUND(i.item_cost::numeric, 2) AS item_cost,
    ROUND((i.item_cost / NULLIF(rt.total_cost, 0) * 100)::numeric, 1)
        AS cost_pct
FROM items AS i
INNER JOIN recipe_totals AS rt ON i.recipe_id = rt.recipe_id
INNER JOIN {{ ref('dim_recipe') }} AS d ON i.recipe_id = d.recipe_id
