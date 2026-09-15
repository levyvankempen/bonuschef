-- Proves the collapse did not attach a discount from a product that cannot
-- actually satisfy the ingredient.

SELECT i.store_id, i.recipe_id, i.item_key, i.offer_product_link
FROM {{ ref('fct_recipe_opportunity_items') }} AS i
LEFT JOIN {{ ref('int_recipe_item_candidates') }} AS c
    ON i.recipe_id = c.recipe_id
    AND i.item_key = c.item_key
    AND i.offer_product_link = c.product_link
WHERE i.offer_product_link IS NOT NULL AND c.product_link IS NULL
