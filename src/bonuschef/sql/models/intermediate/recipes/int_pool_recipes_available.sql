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
-- Deliberately NOT excluding what anybody has adopted or rejected any more.
--
-- Those exclusions were global, so one person adopting a recipe removed it
-- from everybody's suggestions, and one person's "Niet voor mij" hid it from
-- all of them permanently. With one user that was the intended behaviour;
-- with two it is one person deciding for the other.
--
-- The exclusion moved to the portal, which knows who is asking. It stays out
-- of here on purpose rather than gaining an account dimension: this model is
-- ~2,000 rows and is the spine of the Vanavond ranking, so multiplying it by
-- the number of accounts would cost far more than filtering a few hundred
-- rows at read time.
