{{ config(materialized='table') }}

-- The store spine.
--
-- This is the only model in the project that manufactures store_id, and
-- int_recipe_item_opportunity is the only model allowed to CROSS JOIN it. That
-- restriction is what keeps store-scoped, hours-perishable clearance out of the
-- comparable cost history by dependency shape rather than by a filter someone
-- can forget to write.
--
-- clearance_is_current is published but deliberately not *used* by any model
-- downstream: CURRENT_DATE in dbt is evaluated when the model is built, so a
-- mart that filtered on it would grow more confidently wrong the longer it went
-- unbuilt. The portal decides, at read time, from clearance_scraped_at.

SELECT
    store_id,
    MAX(scraped_at) AS clearance_scraped_at,
    (MAX(scraped_at) AT TIME ZONE 'Europe/Amsterdam')::date = CURRENT_DATE
        AS clearance_is_current
FROM {{ ref('stg_ah__markdowns') }}
GROUP BY store_id
