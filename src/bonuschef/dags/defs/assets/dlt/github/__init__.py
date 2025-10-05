"""GitHub Asset with commit SHA support."""

import dlt
from typing import Any, Optional
from dagster import AssetExecutionContext
from dagster_dlt import DagsterDltResource, dlt_assets
from dlt.sources.rest_api import (
    RESTAPIConfig,
    rest_api_resources,
)

OWNER = "supermarkt"
REPO = "checkjebon"
PATH = "data/supermarkets.json"


@dlt.source(name="github")
def github_source(
    access_token: Optional[str] = dlt.secrets.value,
    commit_sha: Optional[str] = None,
    branch: str = "main",
) -> Any:
    """DLT source that loads data from GitHub JSON file."""
    ref = commit_sha or branch
    raw_path = f"{OWNER}/{REPO}/{ref}/{PATH}"

    config: RESTAPIConfig = {
        "client": {
            "base_url": "https://raw.githubusercontent.com",
            "auth": (
                {"type": "bearer", "token": access_token} if access_token else None
            ),
            "headers": {"User-Agent": "dlt-pipeline"},
        },
        "resource_defaults": {
            "write_disposition": "append",
        },
        "resources": [
            {
                "name": "products",
                "table_name": "github__products",
                "endpoint": {
                    "path": raw_path,
                    "data_selector": "$[?(@.n=='ah')].d[*]",
                },
                "primary_key": "l",
            },
        ],
    }

    yield from rest_api_resources(config)


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
def github__products_assets(context: AssetExecutionContext, dlt: DagsterDltResource):
    yield from dlt.run(context=context)
