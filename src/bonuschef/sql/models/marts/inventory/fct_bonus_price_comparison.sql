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
        -- NULL dates mean open, not excluded. AH ships promotions carrying no
        -- dates at all, and `bonus_start_date <= CURRENT_DATE` is NULL rather
        -- than false for those, so they were dropped by three-valued logic
        -- without appearing anywhere as rejected. Two standing Robijn volume
        -- discounts were missing from the comparison for exactly this reason,
        -- and the only visible symptom was a data test counting rows it could
        -- not account for.
        --
        -- This is the same mistake the sentinel note below describes, made
        -- again in the other direction: an absent bound is not a failed one.
        AND (bonus_start_date IS null OR bonus_start_date <= CURRENT_DATE)
        -- An open-ended offer satisfies this naturally. There is deliberately
        -- no upper bound: an earlier version rejected 2999-12-31 as a stale
        -- sentinel, which silently excluded every standing volume discount.
        -- What guards against a stale feed is source freshness, not a date -
        -- if the feed stopped loading, every row in it is suspect whatever its
        -- end date says.
        AND (bonus_end_date IS null OR bonus_end_date >= CURRENT_DATE)

),

matched AS (

    SELECT
        -- Driven by the promotion, not by our catalogue. The retailer's own
        -- claim is the thing being reported; whether we have ever priced the
        -- product independently is a separate question, and answering "no"
        -- must not delete the claim.
        bp.webshop_id,
        cw.product_link,
        -- Fall back to the promotion's own name, so an unreconciled row is
        -- still readable by a person rather than an id with a price.
        COALESCE(cw.product_name, bp.product_name) AS product_name,
        cw.tracked_price,
        cw.price_observed_at,
        cw.price_age_days,
        bp.price_before_bonus AS ah_price,
        bp.bonus_price,
        bp.bonus_mechanism,
        bp.bonus_start_date,
        bp.bonus_end_date,
        bp.bonus_is_ongoing,
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
    -- LEFT, and driven from the feed. An INNER JOIN here dropped every
    -- promoted product we have never seen a price for, so its advertised
    -- saving was not reported as unknown - it was not reported at all, and
    -- nothing counted what went missing. The clearance mart has always done
    -- it this way; this one did not.
    FROM live_bonus AS bp
    LEFT JOIN crosswalk AS cw
        ON bp.webshop_id = cw.webshop_id

)

-- When this answer was computed. The portal's freshness banner used to read
-- the source table's loaded_at, so a successful dlt load followed by a failed
-- dbt rebuild left the banner quiet while every figure on the page was frozen
-- at the last good build. An answer is only as fresh as the older of the feed
-- it came from and the build that produced it.
SELECT
    *,
    CURRENT_TIMESTAMP AS built_at
FROM matched
