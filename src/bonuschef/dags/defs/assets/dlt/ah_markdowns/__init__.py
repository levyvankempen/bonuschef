"""Albert Heijn store markdown ("laatste kans koopjes") asset.

Loads store-specific clearance items (reduced-to-clear / discontinued stock)
from AH's member GraphQL API. Unlike the national bonus feed, this is:

- store-specific (keyed on ``store_id``, resolved from a postal code once),
- member-gated (needs a refresh token, see ``utils/ah_login.py``),
- ephemeral and time-varying — the same item's discount deepens through the
  day (e.g. -25% at midday, -40% near closing) and stock falls as it sells.

Because the discount changes intraday, this source is **append-only**: every
run writes a fresh snapshot tagged with ``scraped_at`` so downstream models can
reconstruct each item's markdown curve. Run it several times a day.
"""

from datetime import datetime, timezone

import dlt
from dagster import AssetExecutionContext, RetryPolicy, asset

from bonuschef.config import AHMarkdownConfig
from bonuschef.utils.ah_auth import AHTokenManager, TokenStore

_BARGAIN_ITEMS_QUERY = """query BargainItems($storeId: String!) {
  bargainItems(storeId: $storeId) {
    product { id title brand salesUnitSize }
    categoryTitle
    markdown { markdownType markdownPercentage markdownExpirationDate }
    stock
    bargainPrice { priceWas priceNow }
  }
}"""


def _to_float(value) -> float | None:
    """AH returns prices as strings (e.g. "0.99"); coerce defensively."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def token_manager(cfg: AHMarkdownConfig) -> AHTokenManager:
    """Token manager backed by the configured token file (auto-refreshing)."""
    return AHTokenManager(
        TokenStore(cfg.token_file),
        bootstrap_refresh_token=cfg.refresh_token,
        client_id=cfg.client_id,
    )


def _iter_markdowns(cfg: AHMarkdownConfig, scraped_at: str):
    data = token_manager(cfg).graphql(
        _BARGAIN_ITEMS_QUERY, {"storeId": str(cfg.store_id)}
    )

    for item in data.get("bargainItems") or []:
        product = item.get("product") or {}
        markdown = item.get("markdown") or {}
        price = item.get("bargainPrice") or {}
        yield {
            "store_id": cfg.store_id,
            "webshop_id": product.get("id"),
            "title": product.get("title"),
            "brand": product.get("brand"),
            "sales_unit_size": product.get("salesUnitSize"),
            "category_title": item.get("categoryTitle"),
            "markdown_type": markdown.get("markdownType"),
            "markdown_percentage": markdown.get("markdownPercentage"),
            "markdown_expiration_date": markdown.get("markdownExpirationDate"),
            "stock": item.get("stock"),
            "price_was": _to_float(price.get("priceWas")),
            "price_now": _to_float(price.get("priceNow")),
            "scraped_at": scraped_at,
        }


@dlt.source(name="ah")
def ah_markdowns_source(cfg: AHMarkdownConfig):
    """DLT source loading current store markdowns as an append-only snapshot."""
    scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return dlt.resource(
        lambda: _iter_markdowns(cfg, scraped_at),
        name="store_markdowns",
        table_name="ah__store_markdowns",
        write_disposition="append",
    )


@asset(
    name="ah__store_markdowns",
    group_name="dlt",
    retry_policy=RetryPolicy(max_retries=2, delay=60),
)
def ah__store_markdowns_asset(context: AssetExecutionContext) -> None:
    """Load a snapshot of AH store markdowns (laatste kans koopjes)."""
    cfg = AHMarkdownConfig.from_env()
    pipeline = dlt.pipeline(
        pipeline_name="ah_markdowns_pipeline",
        destination="postgres",
        dataset_name="public",
        progress="log",
    )
    load_info = pipeline.run(ah_markdowns_source(cfg))
    context.log.info(
        f"Loaded AH store markdowns for store {cfg.store_id}: "
        f"loads={len(load_info.loads_ids)}"
    )
