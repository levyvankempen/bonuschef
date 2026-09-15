{{ config(
    materialized='table',
    indexes=[{'columns': ['store_id', 'recipe_id']}]
) }}

-- One row per ingredient line per store: the last grain before aggregation, and
-- the only model in the project that manufactures a store-scoped recipe row.
--
-- Grain: (store_id, recipe_id, item_key).

WITH priced AS (

    -- The ordinary side. Read, never recomputed: this is the same basket that
    -- fct_recipe_cost_latest totals, so the two marts cannot disagree about
    -- what a recipe ordinarily costs.
    SELECT * FROM {{ ref('int_recipe_items_priced') }}

),

reference AS (

    -- How old the ordinary price is. dim_product carries price_age_days but is
    -- a mart; reading the intermediate keeps this layer self-contained.
    SELECT
        product_link,
        snapshot_timestamp AS price_observed_at,
        (CURRENT_DATE - snapshot_timestamp::date) AS price_age_days
    FROM {{ ref('int_product_latest_price') }}

),

-- The concept fan-out collapses here: every candidate product for a line is
-- offered a price, and exactly one survives per (store, recipe, line).
best_offer AS (

    SELECT DISTINCT ON (o.store_id, c.recipe_id, c.item_key)
        o.store_id,
        c.recipe_id,
        c.item_key,
        o.product_link AS offer_product_link,
        o.offer_kind,
        o.offer_price,
        o.advertised_before_price,
        o.stock,
        o.expires_on,
        o.sales_unit_size,
        o.bonus_mechanism,
        o.requires_multibuy
    FROM {{ ref('int_recipe_item_candidates') }} AS c
    INNER JOIN {{ ref('int_product_offer_today') }} AS o
        ON c.product_link = o.product_link
    -- A price obtainable only by buying more than the recipe needs is not a
    -- price this recipe can pay. It is carried separately, below.
    WHERE NOT o.requires_multibuy
    ORDER BY
        o.store_id ASC, c.recipe_id ASC, c.item_key ASC,
        o.offer_price ASC, o.product_link ASC

),

-- The same collapse restricted to promotions. Needed because clearance can be
-- withdrawn at read time, and an item whose best offer was clearance must then
-- fall back to its bonus price rather than to nothing. Subtracting a "clearance
-- component" from the total would get that wrong.
best_bonus_offer AS (

    SELECT DISTINCT ON (o.store_id, c.recipe_id, c.item_key)
        o.store_id,
        c.recipe_id,
        c.item_key,
        o.offer_price AS bonus_offer_price
    FROM {{ ref('int_recipe_item_candidates') }} AS c
    INNER JOIN {{ ref('int_product_offer_today') }} AS o
        ON c.product_link = o.product_link
    WHERE o.offer_kind = 'bonus' AND NOT o.requires_multibuy
    ORDER BY
        o.store_id ASC, c.recipe_id ASC, c.item_key ASC,
        o.offer_price ASC, o.product_link ASC

),

-- Conditional offers, reported but never ranked on.
best_conditional_offer AS (

    SELECT DISTINCT ON (o.store_id, c.recipe_id, c.item_key)
        o.store_id,
        c.recipe_id,
        c.item_key,
        o.offer_price AS conditional_offer_price,
        o.bonus_mechanism AS conditional_mechanism
    FROM {{ ref('int_recipe_item_candidates') }} AS c
    INNER JOIN {{ ref('int_product_offer_today') }} AS o
        ON c.product_link = o.product_link
    WHERE o.requires_multibuy
    ORDER BY
        o.store_id ASC, c.recipe_id ASC, c.item_key ASC,
        o.offer_price ASC, o.product_link ASC

),

joined AS (

    SELECT
        s.store_id,
        p.recipe_id,
        p.item_key,
        p.item_label,
        p.product_link AS ordinary_product_link,
        p.product_name,
        p.price AS price_ordinary,
        COALESCE(p.quantity, 1) AS units,
        p.is_unresolved,
        r.price_observed_at AS ordinary_price_observed_at,
        r.price_age_days AS ordinary_price_age_days,
        -- The whole of "a saving rests on a comparable reference price".
        (
            p.price IS NOT NULL
            AND r.price_age_days IS NOT NULL
            AND r.price_age_days <= {{ var('max_price_age_days') }}
        ) AS reference_is_comparable,
        b.offer_kind,
        b.offer_price,
        b.offer_product_link,
        b.advertised_before_price,
        b.stock,
        b.expires_on,
        b.sales_unit_size,
        b.bonus_mechanism,
        bb.bonus_offer_price,
        bc.conditional_offer_price,
        bc.conditional_mechanism
    FROM priced AS p
    CROSS JOIN {{ ref('int_store') }} AS s
    LEFT JOIN reference AS r
        ON p.product_link = r.product_link
    LEFT JOIN best_offer AS b
        ON b.store_id = s.store_id
        AND b.recipe_id = p.recipe_id
        AND b.item_key = p.item_key
    LEFT JOIN best_bonus_offer AS bb
        ON bb.store_id = s.store_id
        AND bb.recipe_id = p.recipe_id
        AND bb.item_key = p.item_key
    LEFT JOIN best_conditional_offer AS bc
        ON bc.store_id = s.store_id
        AND bc.recipe_id = p.recipe_id
        AND bc.item_key = p.item_key

),

scored AS (

    SELECT
        *,
        -- An offer measured against a reference price older than the threshold
        -- is not a discount of an unknown amount; it is not a discount. LEAST,
        -- not the offer itself: a sibling candidate on clearance may still be
        -- dearer than the product we would ordinarily buy, and a discount must
        -- never make an ingredient more expensive.
        CASE
            WHEN reference_is_comparable AND offer_price IS NOT NULL
                THEN LEAST(price_ordinary, offer_price)
            ELSE price_ordinary
        END AS price_today,
        CASE
            WHEN reference_is_comparable AND bonus_offer_price IS NOT NULL
                THEN LEAST(price_ordinary, bonus_offer_price)
            ELSE price_ordinary
        END AS price_today_bonus_only
    FROM joined

)

SELECT
    *,
    ROUND((units * price_ordinary)::numeric, 2) AS item_cost_ordinary,
    ROUND((units * price_today)::numeric, 2) AS item_cost_today,
    ROUND((units * price_today_bonus_only)::numeric, 2)
        AS item_cost_today_bonus_only,
    ROUND((units * (price_ordinary - price_today))::numeric, 2) AS item_saving,
    ROUND(
        (units * (price_ordinary - price_today_bonus_only))::numeric, 2
    ) AS item_saving_bonus_only,
    -- What the recipe would save if the larger purchase were made. Reported
    -- beside the saving, never added into it.
    CASE
        WHEN reference_is_comparable
            AND conditional_offer_price IS NOT NULL
            AND conditional_offer_price < price_ordinary
            THEN ROUND(
                (units * (price_ordinary - conditional_offer_price))::numeric, 2
            )
    END AS item_conditional_saving,
    -- AH's own claim, carried alongside and never substituted for the observed
    -- figure. NULL when unknown, never zero.
    CASE
        WHEN offer_price IS NOT NULL AND advertised_before_price IS NOT NULL
            THEN ROUND(
                (units * (advertised_before_price - offer_price))::numeric, 2
            )
    END AS item_advertised_saving,
    (price_today < price_ordinary) AS is_discounted,
    -- An offer we had to ignore. Published so that "why is this not cheaper"
    -- has an answer other than silence.
    (
        offer_price IS NOT NULL
        AND NOT reference_is_comparable
    ) AS offer_withheld_stale_reference,
    -- Two ingredient lines can resolve to the same product - "ui" and "rode ui"
    -- are both confirmed against a generic onion pack. That is two shopping
    -- decisions, so the grain is right, but one clearance unit with stock 1
    -- cannot satisfy both. No uniqueness test can see this; carrying the count
    -- is what makes it checkable.
    SUM(
        CASE
            WHEN price_today < price_ordinary AND offer_kind = 'clearance'
                THEN 1 ELSE 0
        END
    ) OVER (PARTITION BY store_id, recipe_id, offer_product_link)
        AS lines_claiming_offer_product
FROM scored
