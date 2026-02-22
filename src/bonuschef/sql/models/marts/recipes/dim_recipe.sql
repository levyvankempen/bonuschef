WITH

stg_recipes AS (

    SELECT * FROM {{ ref('stg_portal__recipes') }}

),

recipes AS (
    SELECT
        recipe_id,
        recipe_name,
        servings
    FROM stg_recipes
)

SELECT *
FROM recipes
