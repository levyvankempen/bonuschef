WITH

int_products AS (

    SELECT * FROM {{ ref('int_products') }}

),

products AS (
    SELECT *
    FROM int_products
)

SELECT *
FROM products
