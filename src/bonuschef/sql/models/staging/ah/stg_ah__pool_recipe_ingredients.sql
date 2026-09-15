WITH source AS (

    SELECT * FROM {{ source('ah', 'pool_recipe_ingredients') }}

)

SELECT
    recipe_id AS ah_recipe_id,
    line_no,
    concept_id,
    concept_name,
    quantity,
    unit,
    raw_text,
    fetched_at::timestamptz AS fetched_at
FROM source
