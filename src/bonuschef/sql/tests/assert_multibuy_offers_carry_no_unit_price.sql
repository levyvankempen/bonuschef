-- The premise this project was warned about, checked rather than believed.
--
-- A reviewer flagged that bonus_price on a "1 + 1 gratis" is a per-unit figure
-- obtainable only by buying two, and that 153 of 256 live promotions were of
-- that kind - a large overstatement waiting to happen. Measured, the two sets
-- are exactly complementary: every multibuy mechanism carries a NULL
-- bonus_price and every priced mechanism is a single-unit one. AH does not
-- publish a per-unit price for a multibuy deal at all.
--
-- So the requires_multibuy machinery downstream is currently inert. It is kept
-- because it is cheap and because this test is what tells us if that ever
-- changes: the day AH starts pricing a "2 voor 4.99" per unit, this fails and
-- the exclusion starts doing real work instead of silently not needing to.

SELECT bonus_mechanism, bonus_price
FROM {{ ref('fct_bonus_price_comparison') }}
WHERE bonus_price IS NOT NULL
    AND (
        bonus_mechanism ~ '^\s*\d+\s*\+\s*\d+'
        OR bonus_mechanism ~* '^\s*[2-9][0-9]*\s+voor\y'
        OR bonus_mechanism ~* '^\s*[2-9][0-9]*e\s'
    )
