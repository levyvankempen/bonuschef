WITH

stg_products AS (
    SELECT * FROM {{ ref('stg_github__products') }}
),

with_prev AS (
    SELECT
        product_link,
        product_name,
        price,
        snapshot_timestamp,
        LAG(price) OVER (
            PARTITION BY product_link ORDER BY snapshot_timestamp
        ) AS prev_price,
        LAG(snapshot_timestamp) OVER (
            PARTITION BY product_link ORDER BY snapshot_timestamp
        ) AS prev_snapshot_timestamp
    FROM stg_products
),

changes AS (
    SELECT
        product_link,
        product_name,
        prev_snapshot_timestamp,
        snapshot_timestamp,
        prev_price,
        price AS new_price,
        ROUND((price - prev_price)::numeric, 2) AS price_change,
        ROUND(
            ((price - prev_price) / NULLIF(prev_price, 0) * 100)::numeric, 1
        ) AS pct_change
    FROM with_prev
    WHERE prev_price IS NOT NULL
      AND price != prev_price
)

SELECT * FROM changes
