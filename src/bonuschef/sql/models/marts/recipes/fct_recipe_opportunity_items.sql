-- The named ingredients behind a ranking row, and the per-ingredient answer to
-- why a recipe is not ranked.
--
-- Grain: (store_id, recipe_id, item_key). Published at the full grain rather
-- than filtered to discounted lines: an excluded recipe needs its unresolved
-- line visible, and "the rest of the basket did not move" is itself an answer.

SELECT
    store_id,
    recipe_id,
    item_key,
    concept_id,
    item_label,
    product_name,
    ordinary_product_link,
    offer_product_link,
    units,
    sales_unit_size,
    price_ordinary,
    price_today,
    item_cost_ordinary,
    item_cost_today,
    item_saving,
    item_conditional_saving,
    item_advertised_saving,
    offer_kind,
    offer_price,
    bonus_mechanism,
    conditional_mechanism,
    stock,
    expires_on,
    lines_claiming_offer_product,
    is_discounted,
    is_unresolved,
    reference_is_comparable,
    offer_withheld_stale_reference,
    ordinary_price_observed_at,
    ordinary_price_age_days
FROM {{ ref('int_recipe_item_opportunity') }}
