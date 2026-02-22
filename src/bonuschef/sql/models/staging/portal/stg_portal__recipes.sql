WITH

source AS (

    SELECT * FROM {{ source('portal', 'recipes') }}

),

recipes AS (

    SELECT

        recipe_id,
        recipe_name,
        servings

    FROM source
)

SELECT * FROM recipes
