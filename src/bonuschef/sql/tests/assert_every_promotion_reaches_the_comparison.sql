-- Every live promotion must appear in the comparison, priced or not.
--
-- The mart used to be driven by our own catalogue with an INNER JOIN, so a
-- promoted product we had never seen a price for was not reported with its
-- observed saving unknown - it was not reported at all. Measured on live data
-- the day this was found: 1,544 promotions, 432 reconcilable, 1,112 silently
-- dropped. Seventy-two per cent of the feed.
--
-- Nothing counted them, which is why it survived: the mart looked healthy
-- because every row in it was correct. It was the absent rows that were wrong.

SELECT b.webshop_id
FROM {{ ref('stg_ah__bonus_products') }} AS b
LEFT JOIN {{ ref('fct_bonus_price_comparison') }} AS c
    ON b.webshop_id = c.webshop_id
WHERE b.is_bonus
  AND c.webshop_id IS NULL
