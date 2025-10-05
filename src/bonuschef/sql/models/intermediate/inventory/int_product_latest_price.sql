WITH stg_products AS (

    SELECT * FROM {{ ref('stg_github__products') }}

),

latest_timestamp AS (
    SELECT
        product_link,
        MAX(snapshot_timestamp) AS latest_snapshot
    FROM stg_products
    GROUP BY product_link
),

products AS (
    SELECT s.*
    FROM stg_products AS s
    INNER JOIN latest_timestamp AS l
        ON
            s.product_link = l.product_link
            AND s.snapshot_timestamp = l.latest_snapshot
)

SELECT *
FROM products
