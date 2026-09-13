{{ config(indexes=[{'columns': ['product_link'], 'unique': True}]) }}

WITH

int_product_latest_price AS (

    SELECT * FROM {{ ref('int_product_latest_price') }}

),

product_images AS (

    SELECT * FROM {{ ref('stg_portal__product_images') }}

)

SELECT
    p.product_link,
    p.product_url,
    p.product_name,
    p.amount,
    pi.image_url,
    -- Price and its provenance live here so consumers stop joining back to
    -- int_product_latest_price, which this dimension is already built from.
    -- price_age_days is what lets a consumer decide whether a comparison
    -- against this price means anything: a third of the catalogue was last
    -- observed in 2025-11.
    p.price,
    p.snapshot_timestamp AS price_observed_at,
    (CURRENT_DATE - p.snapshot_timestamp::date) AS price_age_days
FROM int_product_latest_price AS p
LEFT JOIN product_images AS pi
    ON p.product_link = pi.product_link
