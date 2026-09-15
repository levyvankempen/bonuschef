-- Every recipe the user has, however it arrived.
--
-- Deliberately NOT the recipe pool. The pool is a few thousand suggestions from
-- AH's catalogue; folding it in here would put 2,000 strangers' recipes on the
-- "Mijn recepten" page and into fct_recipe_cost_history, which exists to track
-- how *your* meals change in price. The opportunity ranking unions the two for
-- itself - see int_pool_recipes_available.
--
-- Both paths land here so that nothing downstream has to know whether a recipe
-- was typed or adopted. AH's ids are large and disjoint from the hand-entered
-- sequence, so the two namespaces coexist without a discriminator in the key.

WITH hand_entered AS (

    SELECT
        recipe_id,
        recipe_name,
        servings,
        'manual' AS source_kind,
        CAST(NULL AS text) AS url,
        CAST(NULL AS text) AS image_url
    FROM {{ ref('stg_portal__recipes') }}

),

adopted AS (

    SELECT
        ah_recipe_id AS recipe_id,
        recipe_name,
        servings,
        'catalogue' AS source_kind,
        url,
        image_url
    FROM {{ ref('stg_portal__ah_recipes') }}

)

SELECT * FROM hand_entered
UNION ALL
SELECT * FROM adopted
