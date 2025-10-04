from typing import Any, Optional
import dlt

from dagster import AssetExecutionContext
from dagster_dlt import DagsterDltResource, dlt_assets
from dlt.sources.rest_api import (
    RESTAPIConfig,
    rest_api_resources,
)

RAW_PATH = "supermarkt/checkjebon/main/data/supermarkets.json"


@dlt.source(name="github")
def github_source(access_token: Optional[str] = dlt.secrets.value) -> Any:
    config: RESTAPIConfig = {
        "client": {
            "base_url": "https://raw.githubusercontent.com",
            "auth": (
                {"type": "bearer", "token": access_token} if access_token else None
            ),
            "headers": {"User-Agent": "dlt-pipeline"},
        },
        "resource_defaults": {
            "write_disposition": "merge",
        },
        "resources": [
            {
                "name": "products_ah",
                "endpoint": {
                    "path": RAW_PATH,
                    "data_selector": "$[?(@.n=='ah')].d[*]",
                },
                "primary_key": "l",
            },
        ],
    }

    yield from rest_api_resources(config)


@dlt_assets(
    dlt_source=github_source(),
    dlt_pipeline=dlt.pipeline(
        pipeline_name="supermarket_pipeline",
        dataset_name="public",
        destination="postgres",
        progress="log",
    ),
    name="github",
    group_name="github",
)
def dagster_github_assets(context: AssetExecutionContext, dlt: DagsterDltResource):
    yield from dlt.run(context=context)
