WITH

source AS (

    SELECT * FROM {{ source('portal', 'recipe_ingredients') }}

),

recipe_ingredients AS (

    SELECT

        recipe_id,
        product_name,
        product_link,
        quantity,
        valid_from::timestamp AS valid_from,
        valid_to::timestamp AS valid_to

    FROM source
)

SELECT * FROM recipe_ingredients
