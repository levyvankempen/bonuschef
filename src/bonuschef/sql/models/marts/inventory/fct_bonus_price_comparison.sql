WITH

products AS (

    SELECT * FROM {{ ref('dim_product') }}

),

latest_prices AS (

    SELECT * FROM {{ ref('int_product_latest_price') }}

),

bonus_products AS (

    SELECT * FROM {{ ref('stg_ah__bonus_products') }}

),

matched AS (

    SELECT
        dp.product_link,
        dp.product_name,
        lp.price AS tracked_price,
        bp.price_before_bonus AS ah_price,
        bp.bonus_price,
        bp.bonus_mechanism,
        bp.bonus_start_date,
        bp.bonus_end_date,
        CASE
            WHEN bp.price_before_bonus IS NOT NULL AND lp.price IS NOT NULL
                THEN ROUND((bp.price_before_bonus - lp.price)::numeric, 2)
        END AS price_inflation,
        CASE
            WHEN lp.price IS NOT NULL AND bp.bonus_price IS NOT NULL
                THEN ROUND((lp.price - bp.bonus_price)::numeric, 2)
        END AS real_savings,
        CASE
            WHEN bp.price_before_bonus IS NOT NULL AND bp.bonus_price IS NOT NULL
                THEN ROUND((bp.price_before_bonus - bp.bonus_price)::numeric, 2)
        END AS advertised_savings,
        bp.price_before_bonus IS NOT NULL
            AND lp.price IS NOT NULL
            AND bp.price_before_bonus > lp.price AS is_inflated
    FROM products AS dp
    INNER JOIN latest_prices AS lp
        ON dp.product_link = lp.product_link
    INNER JOIN bonus_products AS bp
        ON CAST(
            REGEXP_REPLACE(
                SPLIT_PART(dp.product_link, '/', 1),
                '[^0-9]', '', 'g'
            ) AS INTEGER
        ) = bp.webshop_id

)

SELECT * FROM matched
