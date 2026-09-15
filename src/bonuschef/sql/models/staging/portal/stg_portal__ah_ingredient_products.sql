WITH

source AS (

    SELECT * FROM {{ source('portal', 'ah_ingredient_products') }}

)

SELECT
    concept_id,
    product_link,
    product_name,
    confirmed_at,
    proposed_at
FROM source
