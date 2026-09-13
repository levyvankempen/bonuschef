WITH

crosswalk AS (

    SELECT * FROM {{ ref('int_product_crosswalk') }}

),

bonus_products AS (

    SELECT * FROM {{ ref('stg_ah__bonus_products') }}

),

live_bonus AS (

    SELECT *
    FROM bonus_products
    WHERE
        is_bonus = true
        AND bonus_start_date <= CURRENT_DATE
        AND bonus_end_date >= CURRENT_DATE
        -- 941 rows carry a 2999-12-31 sentinel. An upper bound states what we
        -- actually mean - this is not a real campaign end date - and survives
        -- AH choosing a different sentinel.
        AND bonus_end_date < DATE '2100-01-01'

),

matched AS (

    SELECT
        cw.product_link,
        cw.product_name,
        cw.tracked_price,
        cw.price_observed_at,
        cw.price_age_days,
        bp.price_before_bonus AS ah_price,
        bp.bonus_price,
        bp.bonus_mechanism,
        bp.bonus_start_date,
        bp.bonus_end_date,
        -- Advertised: AH's own claim, always available.
        CASE
            WHEN
                bp.price_before_bonus IS NOT null AND bp.bonus_price IS NOT null
                THEN ROUND((bp.price_before_bonus - bp.bonus_price)::NUMERIC, 2)
        END AS advertised_savings,
        -- Observed: measured against a price we saw ourselves, and only while
        -- that observation is recent enough to describe the same market. A
        -- third of the catalogue was last seen in 2025-11; a saving against
        -- that is not a saving, it is a comparison across seasons.
        CASE
            WHEN
                cw.tracked_price IS NOT null
                AND bp.bonus_price IS NOT null
                AND cw.price_age_days <= {{ var('max_price_age_days') }}
                THEN ROUND((cw.tracked_price - bp.bonus_price)::NUMERIC, 2)
        END AS real_savings,
        CASE
            WHEN
                bp.price_before_bonus IS NOT null
                AND cw.tracked_price IS NOT null
                AND cw.price_age_days <= {{ var('max_price_age_days') }}
                THEN
                    ROUND(
                        (bp.price_before_bonus - cw.tracked_price)::NUMERIC, 2
                    )
        END AS price_inflation,
        CASE
            WHEN
                bp.price_before_bonus IS NOT null
                AND cw.tracked_price IS NOT null
                AND cw.price_age_days <= {{ var('max_price_age_days') }}
                THEN bp.price_before_bonus > cw.tracked_price
        END AS is_inflated
    FROM crosswalk AS cw
    INNER JOIN live_bonus AS bp
        ON cw.webshop_id = bp.webshop_id

)

SELECT * FROM matched
