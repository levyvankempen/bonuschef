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

),

-- The pool path. Identical in shape to `adopted` because it is the same key:
-- AH's concept id. One confirmed resolution therefore serves a pool recipe and
-- an adopted one alike, which is what makes the review queue worth working
-- through - the effort compounds across every recipe that uses the ingredient.
--
-- int_pool_recipes_available used to apply the adopted/rejected rules. It no
-- longer does, because those rules became personal: one person adopting a
-- recipe removed it from everybody's suggestions, and one "Niet voor mij"
-- hid it from all of them. The portal applies them now, for whoever is
-- asking. This model keeps costing every pool recipe, which is what lets two
-- people be shown different subsets of the same priced set.
pool AS (

    SELECT
        r.recipe_id,
        'c:' || CAST(i.concept_id AS text) AS item_key,
        'concept' AS source_kind,
        i.concept_id,
        MIN(i.concept_name) AS item_label,
        CAST(NULL AS text) AS pinned_product_link,
        1 AS quantity,
        STRING_AGG(i.raw_text, ' + ' ORDER BY i.line_no) AS quantity_text,
        CAST(NULL AS timestamp) AS valid_from,
        CAST(NULL AS timestamp) AS valid_to
    FROM {{ ref('int_pool_recipes_available') }} AS r
    INNER JOIN {{ ref('stg_ah__pool_recipe_ingredients') }} AS i
        ON r.recipe_id = i.ah_recipe_id
    -- An adopted recipe is in `adopted` above AND still in the pool, so
    -- without this its lines arrive twice and the (recipe_id, item_key) grain
    -- declared above is a lie. It was a lie: 24 pairs were duplicated, the
    -- uniqueness test failed, dbt build failed with it, and every job stayed
    -- red for days.
    --
    -- Excluded against stg_portal__ah_recipes specifically, because that is
    -- what `adopted` reads. fct_recipe_opportunity makes the same exclusion
    -- against dim_recipe, because that is what ITS sibling branch reads, and
    -- the two differ: a deleted recipe leaves dim_recipe but stays in
    -- ah_recipes. Deduping both against one of them would either leave a
    -- duplicate or drop a recipe out of the pool entirely.
    WHERE
        r.recipe_id NOT IN (
            SELECT adopted_recipes.ah_recipe_id
            FROM {{ ref('stg_portal__ah_recipes') }} AS adopted_recipes
        )
    GROUP BY r.recipe_id, i.concept_id

)

SELECT * FROM hand_entered
UNION ALL
SELECT * FROM adopted
UNION ALL
SELECT * FROM pool
