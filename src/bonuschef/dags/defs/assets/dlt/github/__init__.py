"""GitHub Asset with commit SHA support."""

import os
import dlt
import requests
from typing import Any, Optional, Union, Dict, List
from datetime import datetime, timezone
from dagster import (
    AssetExecutionContext,
    asset,
    StaticPartitionsDefinition,
    RetryPolicy,
)
from bonuschef.dags.defs.utils.github_commit_helper import commits_since_date

OWNER = os.getenv("GITHUB_OWNER")
REPO = os.getenv("GITHUB_REPO")
PATH = os.getenv("GITHUB_PATH")
MSG = os.getenv("GITHUB_MESSAGE_FILTER")
START = os.getenv("GITHUB_START_DATE")
BRANCH = os.getenv("GITHUB_BRANCH")
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
PARTITION_KEYS: List[str] = list(SHA_TO_DT.keys())

PARTITIONS = StaticPartitionsDefinition(partition_keys=PARTITION_KEYS)


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
        write_disposition="merge",
        primary_key=["l", "snapshot_at"],
    )


@asset(
    name="github__products",
    group_name="dlt",
    partitions_def=PARTITIONS,
    retry_policy=RetryPolicy(max_retries=2, delay=60),
)
def github__products_assets(context: AssetExecutionContext) -> None:
    """Asset to backfill GitHub product data for all commit SHAs."""
    sha = context.partition_key
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
        f"Loaded sha={commit_sha} snapshot_at={snapshot_at} packages={len(load_info.loads_ids)}"
    )
