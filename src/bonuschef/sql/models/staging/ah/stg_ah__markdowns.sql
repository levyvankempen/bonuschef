WITH

source AS (

    SELECT * FROM {{ source('ah', 'store_markdowns') }}

),

renamed AS (

    SELECT
        store_id,
        webshop_id,
        title AS product_name,
        brand,
        sales_unit_size,
        category_title,
        markdown_type,
        markdown_percentage,
        markdown_expiration_date::date AS markdown_expiration_date,
        stock,
        price_was,
        price_now,
        scraped_at::timestamp AS scraped_at,
        ROUND((price_was - price_now)::numeric, 2) AS markdown_amount

    FROM source
    WHERE webshop_id IS NOT NULL

)

SELECT * FROM renamed
