-- An error now, not a warning.
--
-- It was a warning because the condition was reachable: the saving was summed
-- across every line claiming a clearance unit, so two ingredients resolving to
-- one pack with stock 1 both took the discount and the recipe claimed twice
-- what it could buy. The test detected that and, being a warning, told nobody.
--
-- Clearance is now allocated by claim order, so a line past the stock falls
-- back to its bonus-only price. The condition is impossible by construction,
-- which is what makes an error the right severity: if it fires again, the
-- allocation has broken rather than the data being unusual.
{{ config(severity='error') }}

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
WHERE
    is_discounted
    AND offer_kind = 'clearance'
    AND stock IS NOT NULL
    AND stock < lines_claiming_offer_product
