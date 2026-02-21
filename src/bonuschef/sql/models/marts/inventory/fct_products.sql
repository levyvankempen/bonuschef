WITH

stg_products AS (

    SELECT * FROM {{ ref('stg_github__products') }}

)

SELECT
    product_link,
    price,
    sha AS snapshot_sha,
    snapshot_timestamp
FROM stg_products
