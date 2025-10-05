WITH

int_recipe_items_resolved AS (

    SELECT * FROM {{ ref('int_recipe_items_resolved') }}

),

int_product_latest_price AS (

    SELECT * FROM {{ ref('int_product_latest_price') }}

),

priced_recipes AS (
    SELECT
        t1.recipe_id,
        t1.product_link,
        t1.quantity,
        t2.product_name,
        t2.price,
        (COALESCE(t1.quantity, 1) * COALESCE(t2.price, 0)) AS item_cost
    FROM int_recipe_items_resolved AS t1
    INNER JOIN int_product_latest_price AS t2
        ON t1.product_link = t2.product_link
)

SELECT *
FROM priced_recipes
