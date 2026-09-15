-- The same invariant as assert_no_saving_against_stale_price, over the other
-- mart that publishes a saving to a person.
--
-- That test guards fct_recipe_opportunity_items only, so this model escaped it
-- for as long as it existed: it recomputed real_savings from
-- int_product_latest_price at any age, while the figure it should have used was
-- sitting on the joined row already withheld. Vanavond refused to count a
-- 309-day-old reference; Recepten showed "je bespaart EUR 0.70" for the same
-- offer on the same day.

SELECT
    b.recipe_id,
    b.product_name,
    b.real_savings,
    cw.price_age_days
FROM {{ ref('fct_recipe_cost_breakdown_bonus') }} AS b
INNER JOIN {{ ref('int_product_crosswalk') }} AS cw
    ON b.product_link = cw.product_link
WHERE b.real_savings IS NOT NULL
    AND (
        cw.price_age_days IS NULL
        OR cw.price_age_days > {{ var('max_price_age_days') }}
    )
