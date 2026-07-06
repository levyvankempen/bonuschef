WITH

markdowns AS (

    SELECT * FROM {{ ref('stg_ah__markdowns') }}

),

latest_scrape AS (

    SELECT
        store_id,
        webshop_id,
        MAX(scraped_at) AS latest_scraped_at
    FROM markdowns
    GROUP BY store_id, webshop_id

),

current_markdowns AS (

    SELECT m.*
    FROM markdowns AS m
    INNER JOIN latest_scrape AS ls
        ON
            m.store_id = ls.store_id
            AND m.webshop_id = ls.webshop_id
            AND m.scraped_at = ls.latest_scraped_at

),

tracked_products AS (

    SELECT
        product_link,
        image_url
    FROM {{ ref('dim_product') }}

),

latest_price AS (

    SELECT
        product_link,
        price
    FROM {{ ref('int_product_latest_price') }}

),

-- Map each AH webshop_id to a single tracked product. The product_link's
-- leading segment carries the numeric id; a webshop_id can match more than one
-- link, so keep one deterministically to preserve the one-row-per-item grain.
product_crosswalk AS (

    SELECT DISTINCT ON (webshop_id)
        webshop_id,
        product_link,
        image_url,
        tracked_price
    FROM (
        SELECT
            NULLIF(
                REGEXP_REPLACE(
                    SPLIT_PART(tp.product_link, '/', 1), '[^0-9]', '', 'g'
                ),
                ''
            )::integer AS webshop_id,
            tp.product_link,
            tp.image_url,
            lp.price AS tracked_price
        FROM tracked_products AS tp
        LEFT JOIN latest_price AS lp
            ON tp.product_link = lp.product_link
    ) AS candidates
    WHERE webshop_id IS NOT NULL
    ORDER BY webshop_id, product_link

),

joined AS (

    SELECT
        cm.store_id,
        cm.webshop_id,
        cm.product_name,
        cm.brand,
        cm.sales_unit_size,
        cm.category_title,
        cm.markdown_type,
        cm.markdown_percentage,
        cm.markdown_expiration_date,
        cm.stock,
        cm.price_was,
        cm.price_now,
        cm.markdown_amount,
        cm.scraped_at,
        pc.product_link,
        pc.image_url,
        pc.tracked_price,
        CASE
            WHEN pc.tracked_price IS NOT NULL AND cm.price_now IS NOT NULL
                THEN ROUND((pc.tracked_price - cm.price_now)::numeric, 2)
        END AS real_savings_vs_tracked
    FROM current_markdowns AS cm
    LEFT JOIN product_crosswalk AS pc
        ON cm.webshop_id = pc.webshop_id

)

SELECT * FROM joined
