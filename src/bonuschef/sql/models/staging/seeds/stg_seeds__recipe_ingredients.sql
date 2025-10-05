WITH

source AS (

    SELECT * FROM {{ ref('recipe_ingredients') }}

),

recipe_ingredients AS (

    SELECT

        recipe_id,
        product_name,
        product_link,
        quantity

    FROM source
)

SELECT * FROM recipe_ingredients
