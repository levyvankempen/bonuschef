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

from sqlalchemy import create_engine, text

from bonuschef.config import AHMarkdownConfig, DatabaseConfig
from bonuschef.utils.ah_auth import AHTokenManager, TokenStore


class AHMarkdownsUnavailable(RuntimeError):
    """Every store failed. One failing is a warning; all of them is the feed."""


_BARGAIN_ITEMS_QUERY = """query BargainItems($storeId: String!) {
  bargainItems(storeId: $storeId) {
    product { id title brand salesUnitSize imagePack { medium { url } } }
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


def _image_url(product: dict) -> str | None:
    """A thumbnail for the clearance card, or None.

    AH returns ``imagePack`` as a list of packs, each carrying named sizes.
    Nothing about that shape is documented, so every step degrades to None
    rather than raising: a missing picture is never worth failing a scrape over,
    and the card already renders without one.

    ``medium`` by name rather than by index - the pack's ordering is not
    specified and an index would break silently the day it changes.
    """
    pack = product.get("imagePack")
    if not isinstance(pack, list):
        return None
    for entry in pack:
        if not isinstance(entry, dict):
            continue
        for size in ("medium", "small", "large"):
            node = entry.get(size)
            if isinstance(node, dict) and node.get("url"):
                return str(node["url"])
    return None


def token_manager(cfg: AHMarkdownConfig) -> AHTokenManager:
    """Token manager backed by the configured token file (auto-refreshing)."""
    return AHTokenManager(
        TokenStore(cfg.token_file),
        bootstrap_refresh_token=cfg.refresh_token,
        client_id=cfg.client_id,
    )


def stores_to_scrape(engine, fallback: int) -> list[int]:
    """Every store an account reads, plus the configured one.

    The configured store stays in the list so a deployment with no accounts -
    or one where nobody has chosen a shop yet - keeps working exactly as it
    did. It is a floor, not a default: an account that has chosen is never
    overridden by it.

    Read at run time rather than from configuration, because the answer
    changes when somebody signs up and nothing should have to be redeployed
    for their prices to appear.
    """
    chosen: set[int] = {fallback}
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT DISTINCT store_id FROM public.accounts "
                "WHERE store_id IS NOT NULL"
            )
        ).fetchall()
    chosen.update(int(row[0]) for row in rows)
    return sorted(chosen)


def _iter_markdowns(cfg: AHMarkdownConfig, scraped_at: str, store_id: int):
    data = token_manager(cfg).graphql(_BARGAIN_ITEMS_QUERY, {"storeId": str(store_id)})

    for item in data.get("bargainItems") or []:
        product = item.get("product") or {}
        markdown = item.get("markdown") or {}
        price = item.get("bargainPrice") or {}
        yield {
            "store_id": store_id,
            "webshop_id": product.get("id"),
            "title": product.get("title"),
            "brand": product.get("brand"),
            "sales_unit_size": product.get("salesUnitSize"),
            "image_url": _image_url(product),
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
def ah_markdowns_source(cfg: AHMarkdownConfig, stores: list[int], context=None):
    """Every store's markdowns, in one load.

    A loop rather than a partitioned asset per store. The run queue holds one
    slot deliberately - dbt's setup is not safe to run twice at once - and the
    rebuild downstream of this is inherently all-stores, so partitions would
    turn ten runs a day into forty serialised ones, each paying the process
    startup that dominates this job. Measured previously: 35 of its 39 seconds
    was spawning, which is why it uses the in-process executor.

    One store failing does not stop the others. The asset fails only when
    every store failed, because a friend whose shop is briefly unreachable
    should not stop the rest of the household's prices from loading - and an
    exception here would page whoever is on the other end of the failure
    sensor, hourly, for one broken store.
    """
    scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _all():
        failures: list[str] = []
        for store_id in stores:
            try:
                yield from _iter_markdowns(cfg, scraped_at, store_id)
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                failures.append(f"{store_id}: {type(exc).__name__}")
                if context is not None:
                    context.log.warning(
                        "store %s could not be scraped: %s", store_id, exc
                    )
        if failures and len(failures) == len(stores):
            raise AHMarkdownsUnavailable(
                "no store could be scraped: " + ", ".join(failures)
            )

    return dlt.resource(
        _all,
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
    stores = stores_to_scrape(
        create_engine(DatabaseConfig.from_env().url), cfg.store_id
    )
    context.log.info("Scraping %d store(s): %s", len(stores), stores)
    load_info = pipeline.run(ah_markdowns_source(cfg, stores, context))
    context.add_output_metadata({"stores": stores, "store_count": len(stores)})
    context.log.info(
        f"Loaded AH store markdowns for {len(stores)} store(s): "
        f"loads={len(load_info.loads_ids)}"
    )
