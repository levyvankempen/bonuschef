{{ config(materialized='table') }}

-- Exactly one row per ingredient line, priced or not.
--
-- This used to INNER JOIN the latest price, which meant an ingredient nobody
-- could price simply vanished and the recipe silently got cheaper. The
-- placeholder row below is what makes an unresolved ingredient survive every
-- join and every COUNT(*) downstream, so that only COUNT(price) - the
-- numerator, never the denominator - declines to count it.

WITH items AS (

    SELECT * FROM {{ ref('int_recipe_items_resolved') }}

),

candidates AS (

    -- Hand-entered: the pinned product is its own candidate set, of size one.
    SELECT
        i.recipe_id,
        i.item_key,
        i.pinned_product_link AS product_link
    FROM items AS i
    WHERE i.source_kind = 'direct'

    UNION ALL

    -- Adopted: every product attached to the concept. Several may satisfy it,
    -- and which is cheapest changes from day to day.
    SELECT
        i.recipe_id,
        i.item_key,
        p.product_link
    FROM items AS i
    INNER JOIN {{ ref('stg_portal__ah_ingredient_products') }} AS p
        ON i.concept_id = p.concept_id
    WHERE i.source_kind = 'concept'

),

priced_candidates AS (

    SELECT
        c.recipe_id,
        c.item_key,
        c.product_link,
        lp.product_name,
        lp.price
    FROM candidates AS c
    LEFT JOIN {{ ref('int_product_latest_price') }} AS lp
        ON c.product_link = lp.product_link

),

-- Cheapest priced candidate wins; an item with no candidate at all keeps a row
-- carrying NULLs rather than disappearing.
chosen AS (

    SELECT DISTINCT ON (recipe_id, item_key)
        recipe_id,
        item_key,
        product_link,
        product_name,
        price
    FROM priced_candidates
    ORDER BY
        recipe_id ASC,
        item_key ASC,
        (price IS NULL) ASC,
        price ASC,
        product_link ASC

)

SELECT
    i.recipe_id,
    i.item_key,
    i.source_kind,
    i.concept_id,
    i.item_label,
    i.quantity,
    i.quantity_text,
    i.valid_from,
    i.valid_to,
    c.product_link,
    c.price,
    COALESCE(c.product_name, i.item_label) AS product_name,
    -- No COALESCE on price. An unknown price is unknown; defaulting it to zero
    -- would make the ingredient free and silently understate the recipe.
    (COALESCE(i.quantity, 1) * c.price) AS item_cost,
    (c.product_link IS NULL) AS is_unresolved
FROM items AS i
LEFT JOIN chosen AS c
    ON i.recipe_id = c.recipe_id AND i.item_key = c.item_key
WHERE i.valid_to IS NULL
