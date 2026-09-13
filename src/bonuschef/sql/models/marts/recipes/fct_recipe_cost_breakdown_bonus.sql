WITH

breakdown AS (

    SELECT * FROM {{ ref('fct_recipe_cost_breakdown') }}

),

bonus_products AS (

    SELECT * FROM {{ ref('fct_bonus_price_comparison') }}

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
        bp.ah_price AS price_before_bonus,
        bp.bonus_price,
        bp.product_link IS NOT NULL AS is_on_bonus,
        CASE
            WHEN
                bp.product_link IS NOT NULL
                AND bp.ah_price IS NOT NULL
                AND bp.bonus_price IS NOT NULL
                THEN ROUND(
                    (
                        (bp.ah_price - bp.bonus_price)
                        * COALESCE(b.quantity, 1)
                    )::numeric,
                    2
                )
        END AS advertised_savings,
        CASE
            WHEN
                bp.product_link IS NOT NULL
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
    -- fct_bonus_price_comparison is already filtered to promotions running
    -- today, so is_on_bonus here means "on offer now" rather than "appeared in
    -- a snapshot we happened to take in July".
    LEFT JOIN bonus_products AS bp
        ON b.product_link = bp.product_link
)

SELECT * FROM enriched
