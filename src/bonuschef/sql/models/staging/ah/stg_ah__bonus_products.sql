WITH

source AS (

    SELECT * FROM {{ source('ah', 'bonus_products') }}

),

renamed AS (

    SELECT
        webshop_id,
        title AS product_name,
        bonus_mechanism,
        bonus_start_date::date AS bonus_start_date,
        bonus_end_date::date AS bonus_end_date,
        price_before_bonus,
        bonus_price,
        loaded_at::timestamp AS loaded_at

    FROM source
    WHERE is_bonus = true
)

SELECT * FROM renamed
