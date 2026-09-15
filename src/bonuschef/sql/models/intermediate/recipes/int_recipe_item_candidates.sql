{{ config(materialized='table') }}

-- The exploded candidate set: every product that could satisfy an ingredient
-- line.
--
-- Grain: (recipe_id, item_key, product_link). Deliberately NOT unique on
-- (recipe_id, item_key) - that explosion is the model's whole purpose, and
-- int_recipe_item_opportunity is where it collapses. Naming it as its own model
-- makes the collapse a visible, testable step instead of a subquery nobody
-- reviews.
--
-- Why it exists at all: int_recipe_items_priced already chose one product per
-- line, the cheapest by *tracked* price. The cheapest *today* may be a sibling
-- of that product which happens to be on clearance. Without this model that
-- sibling is invisible, and the many-to-many in ah_ingredient_products - the
-- entire point of the resolution work - is thrown away at the last step.
--
-- The valid_to filter must match int_recipe_items_priced exactly, or the
-- candidate set and the priced set describe different baskets. That is asserted
-- by tests/assert_opportunity_agrees_with_cost_latest.sql.

SELECT
    i.recipe_id,
    i.item_key,
    i.pinned_product_link AS product_link
FROM {{ ref('int_recipe_items_resolved') }} AS i
WHERE
    i.source_kind = 'direct'
    AND i.valid_to IS NULL
    AND i.pinned_product_link IS NOT NULL

UNION

SELECT
    i.recipe_id,
    i.item_key,
    p.product_link
FROM {{ ref('int_recipe_items_resolved') }} AS i
INNER JOIN {{ ref('stg_portal__ah_ingredient_products') }} AS p
    ON i.concept_id = p.concept_id
WHERE i.source_kind = 'concept' AND i.valid_to IS NULL
