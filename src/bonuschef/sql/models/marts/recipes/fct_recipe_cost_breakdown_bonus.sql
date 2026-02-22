WITH

breakdown AS (

    SELECT * FROM {{ ref('fct_recipe_cost_breakdown') }}

),

bonus_products AS (

    SELECT * FROM {{ ref('stg_ah__bonus_products') }}

),

enriched AS (

    SELECT
        b.recipe_id,
        b.recipe_name,
        b.product_name,
        b.product_link,
        b.quantity,
        b.price,
        b.item_cost,
        b.cost_pct,
        bp.bonus_mechanism,
        bp.bonus_start_date,
        bp.bonus_end_date,
        bp.price_before_bonus,
        bp.bonus_price,
        bp.webshop_id IS NOT NULL AS is_on_bonus,
        CASE
            WHEN
                bp.webshop_id IS NOT NULL
                AND bp.price_before_bonus IS NOT NULL
                AND bp.bonus_price IS NOT NULL
                THEN ROUND(
                    (
                        (bp.price_before_bonus - bp.bonus_price)
                        * COALESCE(b.quantity, 1)
                    )::numeric,
                    2
                )
        END AS advertised_savings,
        CASE
            WHEN
                bp.webshop_id IS NOT NULL
                AND b.price IS NOT NULL
                AND bp.bonus_price IS NOT NULL
                THEN ROUND(
                    (
                        (b.price - bp.bonus_price)
                        * COALESCE(b.quantity, 1)
                    )::numeric,
                    2
                )
        END AS real_savings
    FROM breakdown AS b
    LEFT JOIN bonus_products AS bp
        ON (REGEXP_REPLACE(
            SPLIT_PART(b.product_link, '/', 1),
            '[^0-9]', '', 'g'
        ))::integer = bp.webshop_id
)

SELECT * FROM enriched
