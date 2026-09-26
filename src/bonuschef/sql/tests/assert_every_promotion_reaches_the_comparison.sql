-- Every live promotion we could compare must appear in the comparison.
--
-- "Live" is load-bearing and was missing from the WHERE clause for a while:
-- see the note on the date filter at the bottom.
--
-- The mart used to be driven by our own catalogue with an INNER JOIN, so a
-- promoted product we had never seen a price for was not reported with its
-- observed saving unknown - it was not reported at all. Measured on live data
-- the day this was found: 1,544 promotions, 432 reconcilable, 1,112 silently
-- dropped. Seventy-two per cent of the feed.
--
-- Nothing counted them, which is why it survived: the mart looked healthy
-- because every row in it was correct. It was the absent rows that were wrong.
--
-- Scoped to promotions that HAVE a crosswalk entry, which the original was
-- not. A promotion on a product absent from our catalogue has no tracked
-- price and therefore nothing to compare against; demanding it appear asks
-- the mart to invent a row. Measured 2026-09-21: 38 promotions were missing,
-- 36 of them multipacks the catalogue has never carried, and the remaining
-- two a real defect this test was right to surface.
--
-- The count of uncomparable promotions is worth watching, but it is a
-- property of the catalogue's coverage rather than of this mart, so it does
-- not belong in a test that fails the nightly refresh.

SELECT b.webshop_id
FROM {{ ref('stg_ah__bonus_products') }} AS b
INNER JOIN {{ ref('int_product_crosswalk') }} AS x
    ON b.webshop_id = x.webshop_id
LEFT JOIN {{ ref('fct_bonus_price_comparison') }} AS c
    ON b.webshop_id = c.webshop_id
WHERE
    b.is_bonus
    AND c.webshop_id IS NULL
    -- Live, on the same terms the mart uses. Without this the test asked for
    -- rows the mart deliberately does not hold: fct_bonus_price_comparison
    -- filters to promotions whose window includes today, so an expired one
    -- appearing here is the mart being right.
    --
    -- It therefore passed only while the promotional feed was fresh, and the
    -- feed goes stale precisely when the pipeline is red - so once red, this
    -- test helped keep it red. All 167 rows it failed on were promotions whose
    -- window had closed.
    AND (b.bonus_start_date IS NULL OR b.bonus_start_date <= CURRENT_DATE)
    AND (b.bonus_end_date IS NULL OR b.bonus_end_date >= CURRENT_DATE)
