from typing import Any, Optional

import dlt
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
