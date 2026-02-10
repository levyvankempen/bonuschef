WITH

int_product_latest_price AS (

    SELECT * FROM {{ ref('int_product_latest_price') }}

)

SELECT
    product_link,
    product_name,
    amount
FROM int_product_latest_price
