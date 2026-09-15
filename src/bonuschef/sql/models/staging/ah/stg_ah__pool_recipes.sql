WITH source AS (

    SELECT * FROM {{ source('ah', 'pool_recipes') }}

)

SELECT
    recipe_id AS ah_recipe_id,
    title AS recipe_name,
    servings,
    url,
    image_url,
    description,
    cook_time_min,
    rating_average,
    -- Never surfaced without the count. Five stars from three votes is not the
    -- claim five stars from three hundred is.
    rating_count,
    modified_at::timestamptz AS modified_at,
    fetched_at::timestamptz AS fetched_at
FROM source
