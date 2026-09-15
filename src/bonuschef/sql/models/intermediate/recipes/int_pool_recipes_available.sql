{{ config(materialized='table') }}

-- The pool recipes actually on offer to the person today.
--
-- Two rules, and both belong here rather than being repeated at each use:
--   * a pool recipe the person has already adopted is excluded, or it would
--     appear under the same id from two sources and break every grain that
--     counts recipes;
--   * a rejected recipe is excluded entirely. A dismissal is permanent until
--     reversed, and keyed on recipe_id so it survives the weekly refetch - a
--     recipe that climbs back into AH's popular listing must not quietly
--     reappear after someone has said no to it.

SELECT
    p.ah_recipe_id AS recipe_id,
    p.recipe_name,
    p.servings,
    'pool' AS source_kind,
    p.url,
    p.image_url,
    p.rating_average,
    -- Never carried without the count. Five stars from three votes is not the
    -- claim five stars from three hundred is.
    p.rating_count
FROM {{ ref('stg_ah__pool_recipes') }} AS p
LEFT JOIN {{ ref('stg_portal__ah_recipes') }} AS a
    ON p.ah_recipe_id = a.ah_recipe_id
LEFT JOIN {{ ref('stg_portal__ah_recipe_verdicts') }} AS v
    ON p.ah_recipe_id = v.ah_recipe_id
WHERE a.ah_recipe_id IS NULL AND v.ah_recipe_id IS NULL
