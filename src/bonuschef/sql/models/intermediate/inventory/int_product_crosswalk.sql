{{ config(
    materialized='table',
    indexes=[{'columns': ['webshop_id'], 'unique': True}]
) }}

-- The one place where a product's numeric webshop id is derived from its slug.
--
-- Every source names products differently: the GitHub snapshots carry a slug
-- like "wi1408/milka-chocoladereep", the AH bonus and clearance feeds carry a
-- numeric id. Reconciling them used to be inlined in three marts, two of which
-- lacked the NULLIF guard and would raise on the first slug without digits.
--
-- The tie-break matters. AH renames products, so 696 ids map to more than one
-- slug; ordering by slug alphabetically picked the staler row in 340 cases —
-- wi1814 resolved to a price from 2025-11 over one from 2026-09. Recency wins,
-- with the slug retained only to keep the result deterministic.
WITH candidates AS (

    SELECT
        NULLIF(
            REGEXP_REPLACE(SPLIT_PART(product_link, '/', 1), '[^0-9]', '', 'g'),
            ''
        )::bigint AS webshop_id,
        product_link,
        product_name,
        price AS tracked_price,
        snapshot_timestamp AS price_observed_at
    FROM {{ ref('int_product_latest_price') }}

)

SELECT DISTINCT ON (webshop_id)
    webshop_id,
    product_link,
    product_name,
    tracked_price,
    price_observed_at,
    (CURRENT_DATE - price_observed_at::date) AS price_age_days
FROM candidates
WHERE webshop_id IS NOT NULL
ORDER BY webshop_id ASC, price_observed_at DESC, product_link ASC
