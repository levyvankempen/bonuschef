from typing import List, Optional
import dlt
from dagster import (
    AssetExecutionContext,
    asset,
    StaticPartitionsDefinition,
)

from ..github import github_source

HISTORICAL_SHAS: List[str] = [
    "861e8901fb7f15fe1638a0b0b08bed4ef2948652",
    "fc2d3b1731f27065e595fb00bd99ebbd61b85f80",
]

PARTITIONS = StaticPartitionsDefinition(partition_keys=HISTORICAL_SHAS + ["latest"])

@asset(
    name="github__products_backfill",
    group_name="dlt",
    partitions_def=PARTITIONS,
)
def github__products_assets(context: AssetExecutionContext):
    """Materialize one partition per commit SHA (or 'latest' for main branch)."""
    sha = context.partition_key
    commit_sha: Optional[str] = None if sha == "latest" else sha

    dlt_pipeline = dlt.pipeline(
        pipeline_name=f"github_pipeline_{sha}",
        destination="postgres",
        dataset_name="public",
        progress="log",
    )

    load_info = dlt_pipeline.run(
        github_source(
            commit_sha=commit_sha,
            branch="main",
        )
    )

    context.log.info(
        f"Loaded {len(load_info.loads_ids)} load package(s) for partition={sha}"
    )
    return
