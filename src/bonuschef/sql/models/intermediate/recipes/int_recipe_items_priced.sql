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
        -- No COALESCE on price. An unknown price is unknown; defaulting it to
        -- zero would make the ingredient free and silently understate the
        -- recipe the moment the join below is relaxed to a LEFT JOIN.
        (COALESCE(t1.quantity, 1) * t2.price) AS item_cost
    FROM int_recipe_items_resolved AS t1
    INNER JOIN int_product_latest_price AS t2
        ON t1.product_link = t2.product_link
    WHERE t1.valid_to IS NULL
)

SELECT *
FROM priced_recipes
