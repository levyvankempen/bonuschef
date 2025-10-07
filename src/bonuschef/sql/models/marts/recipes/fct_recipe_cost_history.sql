WITH

stg_products AS (
    SELECT * FROM {{ ref('stg_github__products') }}
),

recipe_items AS (
    SELECT * FROM {{ ref('int_recipe_items_resolved') }}
),

dim_recipe AS (
    SELECT * FROM {{ ref('dim_recipe') }}
),

recipe_items_priced_over_time AS (
    SELECT
        i.recipe_id,
        i.product_link,
        i.quantity,
        p.snapshot_timestamp,
        p.price,
        i.quantity * p.price AS item_cost
    FROM recipe_items AS i
    INNER JOIN stg_products AS p
        ON i.product_link = p.product_link
),

agg AS (
    SELECT
        recipe_id,
        snapshot_timestamp,
        round(sum(item_cost)::numeric, 2) AS total_cost
    FROM recipe_items_priced_over_time
    GROUP BY recipe_id, snapshot_timestamp
)

SELECT
    a.recipe_id,
    d.recipe_name,
    d.servings,
    a.snapshot_timestamp,
    a.total_cost,
    round(a.total_cost / nullif(d.servings, 0), 2) AS cost_per_serving
FROM agg AS a
INNER JOIN {{ ref('dim_recipe') }} AS d
    ON a.recipe_id = d.recipe_id
