WITH

source AS (

    SELECT * FROM {{ source('portal', 'product_images') }}

),

product_images AS (

    SELECT

        product_link,
        image_url

    FROM source
)

SELECT * FROM product_images
