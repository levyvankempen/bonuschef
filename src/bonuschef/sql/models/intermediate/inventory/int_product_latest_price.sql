WITH
stg_products AS (

    SELECT * FROM {{ ref('stg_github__products') }}

),

products AS (
    SELECT *
    FROM stg_products
)

SELECT *
FROM products
