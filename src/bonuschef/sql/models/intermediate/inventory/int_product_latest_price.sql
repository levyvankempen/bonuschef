{{ config(
    materialized='table',
    indexes=[{'columns': ['product_link'], 'unique': True}]
) }}

-- The most recent observation of every product we track.
--
-- Materialized as a table deliberately: eight consumers (four tests and four
-- models) read this, and as a view each of them re-derived it from 1.19M rows,
-- spilling the whole CTE to disk and scanning it twice. That was roughly 7 of a
-- 17.5s build.
--
-- DISTINCT ON rather than GROUP BY + self-join: measured 1.1s against 1.7s and
-- avoids the temp spill. The one semantic difference is ties — the self-join
-- returned every row sharing the maximum timestamp, this returns one. There are
-- no ties today and the `unique` test on product_link is what guards it.
SELECT DISTINCT ON (product_link) *
FROM {{ ref('stg_github__products') }}
ORDER BY product_link ASC, snapshot_timestamp DESC
