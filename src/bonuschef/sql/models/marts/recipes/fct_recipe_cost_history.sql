WITH

stg_products AS (SELECT * FROM {{ ref('stg_github__products') }}),

recipe_items AS (SELECT * FROM {{ ref('int_recipe_items_resolved') }}),

snapshots AS (
    SELECT DISTINCT snapshot_timestamp
    FROM stg_products
),

basket AS (
    SELECT
        i.recipe_id,
        i.product_link,
        i.quantity,
        s.snapshot_timestamp
    FROM recipe_items AS i
    CROSS JOIN snapshots AS s
    WHERE
        -- valid_from/valid_to are naive timestamps; snapshot_timestamp is
        -- tz-aware. Without an explicit zone Postgres resolves the naive side
        -- against the session TimeZone, so a dbt run from a laptop in
        -- Europe/Amsterdam would shift every SCD2 boundary by an hour.
        s.snapshot_timestamp
        >= (
            COALESCE(i.valid_from, '1900-01-01'::timestamp)
            AT TIME ZONE 'Europe/Amsterdam'
        )
        AND s.snapshot_timestamp
        < (
            COALESCE(i.valid_to, '9999-12-31'::timestamp)
            AT TIME ZONE 'Europe/Amsterdam'
        )
),

priced AS (
    SELECT
        b.recipe_id,
        b.product_link,
        b.quantity,
        b.snapshot_timestamp,
        p.price,
        (b.quantity * p.price) AS item_cost
    FROM basket AS b
    LEFT JOIN stg_products AS p
        ON
            b.product_link = p.product_link
            AND b.snapshot_timestamp = p.snapshot_timestamp
),

agg AS (
    SELECT
        recipe_id,
        snapshot_timestamp,
        -- NULL when any item is unpriced. SUM skips NULLs, so this used to
        -- publish a partial basket as though it were the whole recipe - and it
        -- is the column the portal charts.
        CASE
            WHEN COUNT(price) = COUNT(*)
                THEN ROUND(SUM(item_cost)::numeric, 2)
        END AS total_cost_observed,
        COUNT(*) AS items_total,
        COUNT(price) AS items_priced,
        COUNT(price)::float / COUNT(*)::float AS price_coverage
    FROM priced
    GROUP BY recipe_id, snapshot_timestamp
)

SELECT
    a.recipe_id,
    d.recipe_name,
    d.servings,
    a.snapshot_timestamp,
    a.total_cost_observed,
    a.price_coverage,
    CASE
        WHEN a.items_priced = a.items_total
            THEN ROUND(a.total_cost_observed / NULLIF(d.servings, 0), 2)
    END AS cost_per_serving_strict
FROM agg AS a
INNER JOIN {{ ref('dim_recipe') }} AS d ON a.recipe_id = d.recipe_id
