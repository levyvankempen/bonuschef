{{ config(severity='warn') }}

-- Two ingredient lines resolving to the same clearance item with too few left
-- for both. A real overstatement, but a legitimate data state - so it warns
-- rather than blocking the build.

SELECT
    store_id,
    recipe_id,
    offer_product_link,
    stock,
    lines_claiming_offer_product
FROM {{ ref('fct_recipe_opportunity_items') }}
WHERE is_discounted
    AND offer_kind = 'clearance'
    AND stock IS NOT NULL
    AND stock < lines_claiming_offer_product
