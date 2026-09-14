WITH

markdowns AS (

    SELECT * FROM {{ ref('stg_ah__markdowns') }}

),

-- "Current" means "present in the most recent scrape of the store". Taking the
-- latest row per *item* instead would keep sold-out items on the page forever,
-- since an item that sold out simply stops appearing in later scrapes.
latest_scrape AS (

    SELECT
        store_id,
        MAX(scraped_at) AS latest_scraped_at
    FROM markdowns
    GROUP BY store_id

),

current_markdowns AS (

    SELECT m.*
    FROM markdowns AS m
    INNER JOIN latest_scrape AS ls
        ON
            m.store_id = ls.store_id
            AND m.scraped_at = ls.latest_scraped_at

),

tracked_products AS (

    SELECT
        product_link,
        image_url
    FROM {{ ref('dim_product') }}

),

-- One shared reconciliation, with a recency-first tie-break. This used to be
-- inlined here and in two other marts with three different behaviours.
product_crosswalk AS (

    SELECT
        cw.webshop_id,
        cw.product_link,
        cw.tracked_price,
        cw.price_age_days,
        dp.image_url
    FROM {{ ref('int_product_crosswalk') }} AS cw
    LEFT JOIN tracked_products AS dp
        ON cw.product_link = dp.product_link

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
        COALESCE(cm.image_url, pc.image_url) AS image_url,
        pc.tracked_price,
        pc.price_age_days,
        -- Withheld, not flagged, when the reference price is too old to be
        -- comparable. A number with a caveat gets read as a number.
        CASE
            WHEN
                pc.tracked_price IS NOT NULL
                AND cm.price_now IS NOT NULL
                AND pc.price_age_days <= {{ var('max_price_age_days') }}
                THEN ROUND((pc.tracked_price - cm.price_now)::numeric, 2)
        END AS real_savings_vs_tracked
    FROM current_markdowns AS cm
    LEFT JOIN product_crosswalk AS pc
        ON cm.webshop_id = pc.webshop_id

)

SELECT * FROM joined
