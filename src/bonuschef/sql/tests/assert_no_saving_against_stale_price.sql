-- The invariant expressed against the raw reference rather than the derived
-- flag, so a bug in reference_is_comparable itself cannot hide it.

SELECT
    i.store_id,
    i.recipe_id,
    i.item_key,
    i.ordinary_price_age_days
FROM {{ ref('fct_recipe_opportunity_items') }} AS i
WHERE
    i.item_saving > 0
    AND (
        i.ordinary_price_age_days IS NULL
        OR i.ordinary_price_age_days > {{ var('max_price_age_days') }}
    )
