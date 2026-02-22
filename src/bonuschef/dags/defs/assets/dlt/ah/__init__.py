"""Albert Heijn bonus products asset via SupermarktConnector."""

from datetime import datetime, timezone

import dlt
from dagster import AssetExecutionContext, RetryPolicy, asset
from supermarktconnector.ah import AHConnector

# search_products() caps at offset 3000 (page * size < 3000).
_PAGE_SIZE = 500
_MAX_PAGES = 6


def _compute_bonus_price(product: dict) -> float | None:
    """Extract the effective per-unit bonus price from a product dict.

    Uses ``currentPrice`` when available (direct price reductions).
    Falls back to calculating from ``discountLabels`` for multi-item promotions.
    """
    if "currentPrice" in product:
        return product["currentPrice"]

    price_before = product.get("priceBeforeBonus")
    labels = product.get("discountLabels", [])
    if not labels or not price_before:
        return None

    label = labels[0]
    code = label.get("code", "")

    if code == "DISCOUNT_FIXED_PRICE":
        return label.get("price")
    if code == "DISCOUNT_X_FOR_Y":
        count = label.get("count", 1)
        return round(label.get("price", 0) / count, 2)
    if code == "DISCOUNT_ONE_FREE":
        count = label.get("count", 2)
        return round(price_before * (count - 1) / count, 2)
    if code == "DISCOUNT_ONE_HALF_PRICE":
        return round(price_before * 0.75, 2)
    if code == "DISCOUNT_X_PLUS_Y_FREE":
        count = label.get("count", 1)
        free = label.get("freeCount", 0)
        return round(price_before * count / (count + free), 2)
    if code == "DISCOUNT_TIERED_PRICE":
        for tier in labels:
            if tier.get("count") == 1:
                return tier.get("price")
        return label.get("price")
    if code == "DISCOUNT_WEIGHT":
        # e.g. "per 500g voor 0.99" — use the fixed price from the label.
        return label.get("price")

    return None


def _iter_search_bonus_products(connector: AHConnector):
    """Paginate through search_products() and yield bonus items.

    The bonuspage API endpoints are unreliable (500/404), so we use the
    product search endpoint instead and filter client-side for isBonus.
    """
    for page in range(_MAX_PAGES):
        try:
            response = connector.search_products(
                query=None, page=page, size=_PAGE_SIZE
            )
        except Exception:
            break

        products = response.get("products", [])
        if not products:
            break

        for product in products:
            if product.get("isBonus"):
                yield product

        total_pages = response.get("page", {}).get("totalPages", 0)
        if page >= total_pages - 1:
            break


@dlt.source(name="ah")
def ah_bonus_source():
    """DLT source that loads current AH bonus products via search endpoint."""

    def _iter_bonus_products():
        connector = AHConnector()
        seen: set[int] = set()
        loaded_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        for product in _iter_search_bonus_products(connector):
            webshop_id = product.get("webshopId")
            if not webshop_id or webshop_id in seen:
                continue
            seen.add(webshop_id)

            labels = product.get("discountLabels", [])
            discount_desc = labels[0].get("defaultDescription") if labels else None

            yield {
                "webshop_id": webshop_id,
                "title": product.get("title"),
                "bonus_mechanism": product.get("bonusMechanism") or discount_desc,
                "bonus_start_date": product.get("bonusStartDate"),
                "bonus_end_date": product.get("bonusEndDate"),
                "price_before_bonus": product.get("priceBeforeBonus"),
                "bonus_price": _compute_bonus_price(product),
                "is_bonus": True,
                "loaded_at": loaded_at,
            }

    return dlt.resource(
        _iter_bonus_products,
        name="bonus_products",
        table_name="ah__bonus_products",
        write_disposition="replace",
        primary_key=["webshop_id"],
    )


@asset(
    name="ah__bonus_products",
    group_name="dlt",
    retry_policy=RetryPolicy(max_retries=2, delay=60),
)
def ah__bonus_products_asset(context: AssetExecutionContext) -> None:
    """Asset to load current AH bonus products via SupermarktConnector."""
    pipeline = dlt.pipeline(
        pipeline_name="ah_bonus_pipeline",
        destination="postgres",
        dataset_name="public",
        progress="log",
    )
    load_info = pipeline.run(ah_bonus_source())
    context.log.info(f"Loaded AH bonus products: loads={len(load_info.loads_ids)}")
