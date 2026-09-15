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
        loaded_at::timestamp AS loaded_at,
        is_bonus,
        -- AH dates open-ended offers 2999-12-31. These are real and live -
        -- "5% volume voordeel" and similar standing shelf discounts, 312 of
        -- them at the time of writing - not stale rows. They are a different
        -- proposition from a "1 + 1 gratis" campaign that ends on Sunday, so
        -- consumers get to tell them apart.
        bonus_end_date::date >= date '2100-01-01' AS bonus_is_ongoing

    FROM source
    -- No is_bonus filter here. Whether a promotion counts as live is a business
    -- rule, and applying it in staging destroyed the "this promotion has ended"
    -- signal at the earliest layer - which is how 199 of 214 rows in
    -- fct_bonus_price_comparison came to be July promotions presented as live.
)

SELECT * FROM renamed
