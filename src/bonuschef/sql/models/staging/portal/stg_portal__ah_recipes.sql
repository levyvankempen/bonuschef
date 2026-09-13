WITH

source AS (

    SELECT * FROM {{ source('portal', 'ah_recipes') }}

)

SELECT
    recipe_id AS ah_recipe_id,
    title AS recipe_name,
    servings,
    url,
    image_url,
    cook_time_min,
    adopted_at
FROM source
