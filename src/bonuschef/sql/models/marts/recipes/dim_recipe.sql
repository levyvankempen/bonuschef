-- Every recipe the user has, however it arrived.
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
