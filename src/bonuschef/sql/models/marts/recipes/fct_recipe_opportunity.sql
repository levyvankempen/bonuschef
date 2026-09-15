-- What is worth cooking today, at one store.
--
-- Grain: (store_id, recipe_id). Every recipe in the pool keeps a row:
-- opportunity_rank is NULL for the ones that are not ranked, and
-- exclusion_reason says why.
--
-- The ranking and the exclusion answer live in one table on purpose. Two tables
-- means two definitions of "eligible" that can drift, and a person asking why
-- their recipe is missing would be answered from a model that was not the one
-- that dropped it. COUNT(*) here is also the honest size of the pool, which the
-- portal is required to show.
--
-- Ranking rests on the *saving*, not on whether the recipe can be fully costed.
-- A saving is a difference, and an ingredient contributing nothing to the
-- difference cannot change it - "at least EUR 3.40 cheaper" is true however
-- many ingredients are unpriced. The total is still withheld unless every
-- ingredient is priced, exactly as fct_recipe_cost_latest withholds it.

WITH items AS (

    SELECT * FROM {{ ref('int_recipe_item_opportunity') }}

),

-- Everything that can be ranked: the person's own recipes and the pool. Unioned
-- here rather than in dim_recipe, which must stay the person's own - putting the
-- pool in there would show 2,000 strangers' recipes on "Mijn recepten" and
-- record their cost in a history that exists to track how *your* meals move.
rankable_recipes AS (

    SELECT
        recipe_id,
        recipe_name,
        servings,
        source_kind,
        url,
        image_url,
        CAST(NULL AS numeric) AS rating_average,
        CAST(NULL AS bigint) AS rating_count
    FROM {{ ref('dim_recipe') }}

    UNION ALL

    SELECT
        recipe_id,
        recipe_name,
        servings,
        source_kind,
        url,
        image_url,
        rating_average::numeric AS rating_average,
        rating_count::bigint AS rating_count
    FROM {{ ref('int_pool_recipes_available') }}

),

agg AS (

    SELECT
        store_id,
        recipe_id,
        COUNT(*) AS items_total,
        COUNT(price_ordinary) AS items_priced,
        COUNT(*) FILTER (WHERE is_unresolved) AS items_unresolved,
        COUNT(*) FILTER (WHERE is_discounted) AS items_discounted,
        COUNT(*) FILTER (WHERE offer_withheld_stale_reference)
            AS items_offer_withheld_stale,
        COUNT(*) FILTER (WHERE is_discounted AND offer_kind = 'clearance')
            AS items_discounted_clearance,
        COUNT(*) FILTER (WHERE item_conditional_saving IS NOT NULL)
            AS items_conditional_offer,

        -- The saving. Summed over what is known, which is why it is a lower
        -- bound rather than an exact figure when coverage is partial.
        ROUND(COALESCE(SUM(item_saving), 0)::numeric, 2) AS saving_total,
        ROUND(
            COALESCE(SUM(item_saving_bonus_only), 0)::numeric, 2
        ) AS saving_bonus_only,
        ROUND(
            COALESCE(SUM(item_conditional_saving), 0)::numeric, 2
        ) AS conditional_saving,
        ROUND(
            COALESCE(SUM(item_advertised_saving), 0)::numeric, 2
        ) AS advertised_saving_total,

        -- Totals are withheld unless the whole basket is priced. A partial sum
        -- is not a total.
        CASE WHEN COUNT(price_ordinary) = COUNT(*)
            THEN ROUND(SUM(item_cost_ordinary)::numeric, 2) END AS cost_ordinary,
        CASE WHEN COUNT(price_ordinary) = COUNT(*)
            THEN ROUND(SUM(item_cost_today)::numeric, 2) END AS cost_today,
        CASE WHEN COUNT(price_ordinary) = COUNT(*)
            THEN ROUND(SUM(item_cost_today_bonus_only)::numeric, 2)
        END AS cost_today_bonus_only,

        -- Urgency comes from clearance lines only. A promotion has neither
        -- stock nor an expiry, so an unfiltered COUNT of NULL stock would mark
        -- every bonus line "unknown" and leave the banner permanently uncertain.
        MIN(stock) FILTER (WHERE is_discounted AND offer_kind = 'clearance')
            AS min_stock_remaining,
        COUNT(*) FILTER (
            WHERE is_discounted AND offer_kind = 'clearance' AND stock IS NULL
        ) AS clearance_items_stock_unknown,
        MIN(expires_on) FILTER (
            WHERE is_discounted AND offer_kind = 'clearance'
        ) AS earliest_expiry,
        COUNT(*) FILTER (
            WHERE is_discounted AND offer_kind = 'clearance'
                AND expires_on IS NULL
        ) AS clearance_items_expiry_unknown,
        BOOL_OR(
            is_discounted AND offer_kind = 'clearance'
            AND stock IS NOT NULL
            AND stock < lines_claiming_offer_product
        ) AS has_insufficient_stock,
        BOOL_OR(units > 1 OR sales_unit_size IS NOT NULL)
            AS saving_covers_whole_packs
    FROM items
    GROUP BY store_id, recipe_id

),

classified AS (

    SELECT
        a.*,
        (a.items_priced > 0) AS is_rankable,
        CASE
            WHEN a.items_total = 0 THEN 'no_ingredients'
            WHEN a.items_priced = 0 THEN 'no_priced_ingredient'
            WHEN a.saving_total <= 0 THEN 'no_discount_today'
        END AS exclusion_reason
    FROM agg AS a

)

SELECT
    c.store_id,
    s.clearance_scraped_at,
    s.clearance_is_current,
    d.recipe_id,
    d.recipe_name,
    d.servings,
    d.source_kind,
    d.url,
    d.image_url,
    d.rating_average,
    d.rating_count,
    c.is_rankable,
    c.exclusion_reason,
    c.cost_ordinary,
    c.cost_today,
    c.cost_today_bonus_only,
    c.saving_total,
    c.saving_bonus_only,
    c.conditional_saving,
    c.advertised_saving_total,
    -- A saving over an incompletely priced recipe is a floor, not a figure, and
    -- the portal must not render the two the same way.
    (c.items_priced < c.items_total) AS saving_is_lower_bound,
    c.saving_covers_whole_packs,
    ROUND(
        (c.saving_total / NULLIF(c.cost_ordinary, 0) * 100)::numeric, 1
    ) AS saving_pct,
    ROUND((c.cost_today / NULLIF(d.servings, 0))::numeric, 2)
        AS cost_today_per_serving,
    c.items_total,
    c.items_priced,
    c.items_unresolved,
    c.items_discounted,
    c.items_discounted_clearance,
    c.items_offer_withheld_stale,
    c.items_conditional_offer,
    c.min_stock_remaining,
    c.clearance_items_stock_unknown,
    c.earliest_expiry,
    c.clearance_items_expiry_unknown,
    c.has_insufficient_stock,
    -- Non-null only for a recipe that is both rankable and actually cheaper.
    -- Everything else keeps its row and its reason.
    CASE WHEN c.is_rankable AND c.saving_total > 0 THEN
        RANK() OVER (
            PARTITION BY c.store_id
            ORDER BY
                CASE WHEN c.is_rankable AND c.saving_total > 0
                    THEN c.saving_total END DESC,
                c.recipe_id ASC
        )
    END AS opportunity_rank
FROM classified AS c
INNER JOIN {{ ref('int_store') }} AS s ON c.store_id = s.store_id
-- INNER is safe: every row in agg came from a recipe item, and every recipe
-- item came from a recipe that is either the person's own or in the pool.
INNER JOIN rankable_recipes AS d ON c.recipe_id = d.recipe_id
