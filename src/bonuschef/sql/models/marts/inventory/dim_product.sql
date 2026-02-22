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
    pi.image_url
FROM int_product_latest_price AS p
LEFT JOIN product_images AS pi
    ON p.product_link = pi.product_link
