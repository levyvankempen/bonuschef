from typing import List
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

SHA_TO_DT = {
    "861e8901fb7f15fe1638a0b0b08bed4ef2948652": "2025-09-29T04:36:12Z",
    "fc2d3b1731f27065e595fb00bd99ebbd61b85f80": "2025-09-22T04:42:07Z",
}

PARTITIONS = StaticPartitionsDefinition(partition_keys=HISTORICAL_SHAS + ["latest"])


@asset(name="github__products_backfill", group_name="dlt", partitions_def=PARTITIONS)
def github__products_assets(context: AssetExecutionContext):
    sha = context.partition_key
    commit_sha = None if sha == "latest" else sha
    snapshot_at = (
        None if sha == "latest" else SHA_TO_DT.get(sha)
    )

    pipeline = dlt.pipeline(
        pipeline_name=f"github_pipeline_{sha}",
        destination="postgres",
        dataset_name="public",
        progress="log",
    )
    load_info = pipeline.run(
        github_source(commit_sha=commit_sha, branch="main", snapshot_at=snapshot_at)
    )
    context.log.info(f"Partition={sha} loaded {len(load_info.loads_ids)} package(s).")
