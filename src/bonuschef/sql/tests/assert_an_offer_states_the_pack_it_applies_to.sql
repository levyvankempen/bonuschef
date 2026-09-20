-- An offer must carry the pack it applies to, when the product states one.
--
-- sales_unit_size was CAST(NULL AS text) for every bonus offer, so the page's
-- "hele verpakking: 500 g" caveat could only ever fire on clearance lines. A
-- recipe needing 100 g of a promoted 500 g pack is costed at the pack -
-- because that is what has to be bought - and nothing on the page explained
-- why the saving looked so large.
--
-- The clearance feed carries its own size; a promotion does not, so it has to
-- come from the product. Only checked where the product states one: plenty
-- have no amount, and inventing a caveat is worse than omitting it.

SELECT o.product_link
FROM {{ ref('int_product_offer_today') }} AS o
INNER JOIN {{ ref('dim_product') }} AS d ON o.product_link = d.product_link
WHERE
    o.sales_unit_size IS NULL
    AND d.amount IS NOT NULL
