WITH

markdowns AS (

    SELECT * FROM {{ ref('stg_ah__markdowns') }}

),

with_curve AS (

    SELECT
        store_id,
        webshop_id,
        product_name,
        brand,
        sales_unit_size,
        category_title,
        markdown_type,
        markdown_percentage,
        markdown_expiration_date,
        stock,
        price_was,
        price_now,
        markdown_amount,
        scraped_at,
        MIN(markdown_percentage) OVER item AS first_markdown_pct,
        MAX(markdown_percentage) OVER item AS max_markdown_pct,
        MIN(scraped_at) OVER item AS first_seen_at,
        MAX(scraped_at) OVER item AS last_seen_at,
        ROW_NUMBER() OVER (
            PARTITION BY store_id, webshop_id ORDER BY scraped_at DESC
        ) AS recency_rank
    FROM markdowns
    WINDOW item AS (PARTITION BY store_id, webshop_id)

)

SELECT
    store_id,
    webshop_id,
    product_name,
    brand,
    sales_unit_size,
    category_title,
    markdown_type,
    markdown_percentage,
    markdown_expiration_date,
    stock,
    price_was,
    price_now,
    markdown_amount,
    scraped_at,
    first_markdown_pct,
    max_markdown_pct,
    first_seen_at,
    last_seen_at,
    recency_rank = 1 AS is_latest
FROM with_curve
