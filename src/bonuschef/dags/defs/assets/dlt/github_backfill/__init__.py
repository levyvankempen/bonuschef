"""Backfill supermarket product data from GitHub."""

import os
import dlt
from typing import Optional, Dict, List
from dagster import AssetExecutionContext, asset, StaticPartitionsDefinition

from ..github import github_source
from bonuschef.dags.defs.utils.github_commit_helper import commits_since_date

OWNER = os.getenv("GITHUB_OWNER")
REPO = os.getenv(
    "GITHUB_REPO",
)
MSG = os.getenv("GITHUB_MESSAGE_FILTER")
START = os.getenv("GITHUB_START_DATE")
BRANCH = os.getenv("GITHUB_BRANCH", "main")
TOKEN = os.getenv("GITHUB_TOKEN")
MAX_PAGES = int(os.getenv("GITHUB_MAX_PAGES"))

_commits = commits_since_date(
    owner=OWNER,
    repo=REPO,
    message_filter=MSG,
    since_iso_utc=START,
    branch=BRANCH,
    token=TOKEN,
    max_pages=MAX_PAGES,
)

SHA_TO_DT: Dict[str, str] = {c["sha"]: c["date"] for c in _commits}
PARTITION_KEYS: List[str] = list(SHA_TO_DT.keys()) + ["latest"]

PARTITIONS = StaticPartitionsDefinition(partition_keys=PARTITION_KEYS)


@asset(
    name="github__products_backfill",
    group_name="dlt",
    partitions_def=PARTITIONS,
)
def github__products_backfill(context: AssetExecutionContext):
    sha = context.partition_key
    if sha == "latest":
        commit_sha: Optional[str] = None
        snapshot_at: Optional[str] = None
    else:
        commit_sha = sha
        snapshot_at = SHA_TO_DT.get(sha)

    pipeline = dlt.pipeline(
        pipeline_name=f"github_pipeline_{sha}",
        destination="postgres",
        dataset_name="public",
        progress="log",
    )
    load_info = pipeline.run(
        github_source(commit_sha=commit_sha, branch=BRANCH, snapshot_at=snapshot_at)
    )
    context.log.info(
        f"Loaded sha={commit_sha or 'latest'} snapshot_at={snapshot_at} packages={len(load_info.loads_ids)}"
    )
