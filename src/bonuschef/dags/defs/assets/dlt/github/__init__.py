"""GitHub Asset with commit SHA support."""

import dlt
import requests
from typing import Any, Optional, Union
from datetime import datetime, timezone
from dagster import AssetExecutionContext
from dagster_dlt import DagsterDltResource, dlt_assets

OWNER = "supermarkt"
REPO = "checkjebon"
PATH = "data/supermarkets.json"


def _snapshot_str(snapshot_at: Optional[Union[str, datetime]]) -> str:
    if snapshot_at is None:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(snapshot_at, datetime):
        return snapshot_at.isoformat()
    return snapshot_at


@dlt.source(name="github")
def github_source(
    access_token: Optional[str] = dlt.secrets.value,
    commit_sha: Optional[str] = None,
    branch: str = "main",
    snapshot_at: Optional[Union[str, datetime]] = None,
) -> Any:
    """DLT source that loads data from GitHub JSON file."""
    ref = commit_sha or branch
    url = f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{ref}/{PATH}"
    headers = {"User-Agent": "dlt-pipeline"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    snapshot_at_str = _snapshot_str(snapshot_at)
    snapshot_sha = commit_sha or "latest"

    def _iter_products():
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        payload = resp.json()

        chain = next((o for o in payload if o.get("n") == "ah"), None)
        if not chain:
            return
        for item in chain.get("d", []):
            item["snapshot_sha"] = snapshot_sha
            item["snapshot_at"] = snapshot_at_str
            yield item

    return dlt.resource(
        _iter_products,
        name="products",
        table_name="github__products",
        write_disposition="append",
        primary_key="l",
    )


dlt_pipeline = dlt.pipeline(
    pipeline_name="github_pipeline",
    destination="postgres",
    dataset_name="public",
    progress="log",
)


@dlt_assets(
    dlt_source=github_source(),
    dlt_pipeline=dlt_pipeline,
    name="github__products_assets",
    group_name="dlt",
)
def github__products_assets(
    context: AssetExecutionContext, dlt: DagsterDltResource
) -> Any:
    """Asset to retrieve data from GitHub JSON file."""
    yield from dlt.run(context=context)
