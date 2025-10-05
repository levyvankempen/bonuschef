WITH

source AS (

    SELECT * FROM {{ ref('recipes') }}

),

recipes AS (

    SELECT

        recipe_id,
        recipe_name,
        servings

    FROM source
)

SELECT * FROM recipes
