WITH

stg_recipes AS (

    SELECT * FROM {{ ref('stg_seeds__recipes') }}

),

stg_recipe_ingredients AS (

    SELECT * FROM {{ ref('stg_seeds__recipe_ingredients') }}

),

resolved_recipes AS (
    SELECT
        t1.recipe_id,
        t1.recipe_name,
        t1.servings,
        t2.product_name,
        t2.product_link,
        t2.quantity
    FROM stg_recipes AS t1
    INNER JOIN stg_recipe_ingredients AS t2
        ON t1.recipe_id = t2.recipe_id
)

SELECT *
FROM resolved_recipes
