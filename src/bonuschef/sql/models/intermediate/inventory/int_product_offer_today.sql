{{ config(
    materialized='table',
    indexes=[{'columns': ['product_link']}]
) }}

-- Every discount available on a tracked product at a store today, collapsed to
-- one row per (store, product).
--
-- This is where the clearance/bonus fan-out dies. Two products are in both sets
-- today - AH Aardappelschijfjes at EUR 0.27 on clearance and EUR 0.89 on bonus,
-- and AH Mini krieltjes likewise - and summing both savings would overstate
-- that single ingredient by EUR 0.30.

WITH clearance_offers AS (

    -- fct_store_clearance is already restricted to the latest scrape and
    -- grained (store_id, webshop_id); the crosswalk gives it at most one
    -- product_link, because webshop_id is derived from the slug by a function.
    SELECT
        c.store_id,
        c.product_link,
        c.webshop_id,
        'clearance' AS offer_kind,
        c.price_now AS offer_price,
        c.price_was AS advertised_before_price,
        c.stock,
        c.markdown_expiration_date AS expires_on,
        c.sales_unit_size,
        CAST(NULL AS text) AS bonus_mechanism,
        FALSE AS bonus_is_ongoing,
        FALSE AS requires_multibuy
    FROM {{ ref('fct_store_clearance') }} AS c
    WHERE c.product_link IS NOT NULL AND c.price_now IS NOT NULL

),

bonus_offers AS (

    -- A promotion is national, so it is an offer at every store we track. The
    -- cross join is bounded by int_store, which has one row today.
    SELECT
        s.store_id,
        b.product_link,
        CAST(NULL AS bigint) AS webshop_id,
        'bonus' AS offer_kind,
        b.bonus_price AS offer_price,
        b.ah_price AS advertised_before_price,
        CAST(NULL AS integer) AS stock,
        -- A promotion carries no expiry here on purpose: bonus_end_date is a
        -- campaign boundary, not a use-by date, and mixing the two would let a
        -- week-long offer masquerade as an item that must be eaten tonight.
        CAST(NULL AS date) AS expires_on,
        CAST(NULL AS text) AS sales_unit_size,
        b.bonus_mechanism,
        b.bonus_is_ongoing,
        -- 146 of 256 live matched promotions are multibuy: bonus_price is the
        -- per-unit price you get only by buying two or more, and a recipe
        -- needing one unit does not get it. Anchored at the start of the
        -- string so "100 GRAM VOOR 1.69" (a unit price) and "VOOR 0.99" (a
        -- single-item price) are not swept in with "2 voor 4.99".
        (
            b.bonus_mechanism ~ '^\s*\d+\s*\+\s*\d+'
            OR b.bonus_mechanism ~* '^\s*[2-9][0-9]*\s+voor\y'
            OR b.bonus_mechanism ~* '^\s*[2-9][0-9]*e\s'
        ) AS requires_multibuy
    FROM {{ ref('fct_bonus_price_comparison') }} AS b
    CROSS JOIN {{ ref('int_store') }} AS s
    -- product_link IS NOT NULL, as the clearance branch above already
    -- requires. The comparison mart deliberately keeps promotions for products
    -- we have never priced - that is the retailer's claim, and reporting it is
    -- the point of that mart. But an offer with no link cannot be attached to
    -- a recipe ingredient, which is what THIS table is for.
    --
    -- Without it the mart's 1,112 unreconcilable promotions arrive here with a
    -- null key and fail this model's own not_null test. That did not show up
    -- when the change landed because int_store was empty in the fixture, so
    -- the cross join produced nothing and the test passed over zero rows.
    WHERE b.bonus_price IS NOT NULL AND b.product_link IS NOT NULL

)

-- Cheapest offer wins. The tie-break prefers 'bonus', which is alphabetically
-- first and deliberately so: at an equal price a promotion running all week
-- beats one unit of clearance that may be gone within the hour.
SELECT DISTINCT ON (store_id, product_link) *
FROM (
    SELECT * FROM clearance_offers
    UNION ALL
    SELECT * FROM bonus_offers
) AS u
ORDER BY store_id ASC, product_link ASC, offer_price ASC, offer_kind ASC
