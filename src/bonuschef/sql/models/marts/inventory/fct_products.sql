{{ config(
    materialized='incremental',
    unique_key=['product_link', 'snapshot_timestamp'],
    incremental_strategy='delete+insert',
    indexes=[
        {'columns': ['product_link']},
        {'columns': ['snapshot_timestamp']}
    ]
) }}

-- 1.19M rows / 157 MB, from a source that is strictly append-only and loads
-- weekly in fixed 16,173-row snapshots. Rebuilding it in full on every run was
-- the largest single piece of wasted work in the build.
--
-- delete+insert rather than append: dlt can replay a load, and append would
-- silently double those rows. The indexes matter because the portal joins this
-- table on every chart and public_marts had none at all.
WITH

stg_products AS (

    SELECT * FROM {{ ref('stg_github__products') }}

)

SELECT
    stg_products.product_link,
    stg_products.price,
    stg_products.sha AS snapshot_sha,
    stg_products.snapshot_timestamp
FROM stg_products
{% if is_incremental() %}
    WHERE stg_products.snapshot_timestamp
    -- noqa: RF02 — the inner reference belongs to {{ this }}, a
    -- different relation that sqlfluff cannot see through.
    > (SELECT MAX(snapshot_timestamp) FROM {{ this }})  -- noqa: RF02
{% endif %}
