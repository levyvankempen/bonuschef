{{ config(materialized='table') }}

-- The store spine.
--
-- This is the only model in the project that manufactures store_id, and
-- int_recipe_item_opportunity is the only model allowed to CROSS JOIN it. That
-- restriction is what keeps store-scoped, hours-perishable clearance out of the
-- comparable cost history by dependency shape rather than by a filter someone
-- can forget to write.
--
-- Built from the stores ACCOUNTS use, not from the stores that happen to have
-- been scraped. It used to be the latter, and the consequence was severe and
-- silent: three models CROSS JOIN this one, so a store with no scrape had no
-- row and therefore no rows anywhere downstream - including national bonus
-- prices, which do not depend on a store at all. A friend who chose a
-- different shop saw an empty application rather than "bonus only", and
-- nothing said why.
--
-- The scraped stores are unioned in as well, so history from a store no
-- account currently uses is not orphaned by somebody changing their mind.
--
-- clearance_scraped_at is therefore nullable now: a store can legitimately
-- have an account and no scrape yet. NULL means "not scraped", which is a
-- different statement from "scraped and found nothing", and the portal has to
-- say them differently.
--
-- clearance_is_current is published but deliberately not *used* by any model
-- downstream: CURRENT_DATE in dbt is evaluated when the model is built, so a
-- mart that filtered on it would grow more confidently wrong the longer it went
-- unbuilt. The portal decides, at read time, from clearance_scraped_at.

WITH stores AS (

    SELECT store_id FROM {{ ref('stg_portal__accounts') }}

    UNION

    SELECT store_id FROM {{ ref('stg_ah__markdowns') }}

),

scrapes AS (

    SELECT
        store_id,
        MAX(scraped_at) AS clearance_scraped_at
    FROM {{ ref('stg_ah__markdowns') }}
    GROUP BY store_id

)

SELECT
    s.store_id,
    c.clearance_scraped_at,
    -- FALSE rather than NULL for a store that has never been scraped: the
    -- question "is this current" has an answer, and it is no.
    COALESCE(
        (c.clearance_scraped_at AT TIME ZONE 'Europe/Amsterdam')::date
        = CURRENT_DATE,
        false
    ) AS clearance_is_current
FROM stores AS s
LEFT JOIN scrapes AS c ON s.store_id = c.store_id
