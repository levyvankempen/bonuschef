{{ config(materialized='table') }}

-- One row per ingredient line, from either path.
--
-- A hand-entered ingredient is the degenerate case of an adopted one: an item
-- whose candidate set was already resolved, to exactly one product. Modelling
-- it that way means nothing below this point has to know which path a recipe
-- came from.
--
-- Grain: (recipe_id, item_key). An adopted recipe collapses repeated concepts
-- onto one line, because "2 uien" and "1 ui, gesnipperd" are one shopping
-- decision and resolving the concept once must serve both.

WITH hand_entered AS (

    SELECT
        r.recipe_id,
        'd:' || i.product_link AS item_key,
        'direct' AS source_kind,
        CAST(NULL AS bigint) AS concept_id,
        i.product_name AS item_label,
        i.product_link AS pinned_product_link,
        i.quantity,
        CAST(NULL AS text) AS quantity_text,
        i.valid_from,
        i.valid_to
    FROM {{ ref('stg_portal__recipes') }} AS r
    INNER JOIN {{ ref('stg_portal__recipe_ingredients') }} AS i
        ON r.recipe_id = i.recipe_id

),

adopted AS (

    SELECT
        -- AH ids are large and disjoint from the hand-entered sequence, so the
        -- two namespaces coexist without a discriminator column.
        r.ah_recipe_id AS recipe_id,
        'c:' || CAST(i.concept_id AS text) AS item_key,
        'concept' AS source_kind,
        i.concept_id,
        MIN(i.concept_name) AS item_label,
        CAST(NULL AS text) AS pinned_product_link,
        -- Costing uses one product per ingredient (see the change design): the
        -- recipe's own amount is carried verbatim for display, not multiplied.
        1 AS quantity,
        STRING_AGG(i.raw_text, ' + ' ORDER BY i.line_no) AS quantity_text,
        CAST(NULL AS timestamp) AS valid_from,
        CAST(NULL AS timestamp) AS valid_to
    FROM {{ ref('stg_portal__ah_recipes') }} AS r
    INNER JOIN {{ ref('stg_portal__ah_recipe_ingredients') }} AS i
        ON r.ah_recipe_id = i.ah_recipe_id
    GROUP BY r.ah_recipe_id, i.concept_id

)

SELECT * FROM hand_entered
UNION ALL
SELECT * FROM adopted
