WITH

int_products AS (

    SELECT * FROM {{ ref("int_product_latest_price") }}

),

products AS (
    SELECT *
    FROM int_products
)

SELECT *
FROM products
