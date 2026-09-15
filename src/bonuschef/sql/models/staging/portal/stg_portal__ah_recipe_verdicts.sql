WITH source AS (

    SELECT * FROM {{ source('portal', 'ah_recipe_verdicts') }}

)

SELECT
    recipe_id AS ah_recipe_id,
    verdict,
    decided_at
FROM source
WHERE verdict = 'rejected'
