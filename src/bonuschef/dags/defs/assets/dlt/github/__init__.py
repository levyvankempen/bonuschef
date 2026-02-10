"""GitHub Asset with dynamic partition discovery via sensor."""

from datetime import datetime, timezone

import dlt
import requests
from dagster import (
    AssetExecutionContext,
    DynamicPartitionsDefinition,
    RetryPolicy,
    asset,
)

from bonuschef.config import GitHubConfig

GITHUB_PARTITIONS = DynamicPartitionsDefinition(name="github_commits")


def _get_commit_date(cfg: GitHubConfig, sha: str) -> str:
    """Fetch the author date for a specific commit SHA."""
    url = f"https://api.github.com/repos/{cfg.owner}/{cfg.repo}/commits/{sha}"
    headers = {"Accept": "application/vnd.github+json"}
    if cfg.token:
        headers["Authorization"] = f"Bearer {cfg.token}"
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()["commit"]["author"]["date"]


def _snapshot_str(snapshot_at: str | datetime | None) -> str:
    if snapshot_at is None:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(snapshot_at, datetime):
        return snapshot_at.isoformat()
    return snapshot_at


@dlt.source(name="github")
def github_source(
    owner: str,
    repo: str,
    path: str,
    access_token: str | None = None,
    commit_sha: str | None = None,
    branch: str = "main",
    snapshot_at: str | datetime | None = None,
):
    """DLT source that loads data from GitHub JSON file."""
    ref = commit_sha or branch
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"
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
    partitions_def=GITHUB_PARTITIONS,
    retry_policy=RetryPolicy(max_retries=2, delay=60),
)
def github__products_assets(context: AssetExecutionContext) -> None:
    """Asset to load GitHub product data for a specific commit SHA."""
    cfg = GitHubConfig.from_env()
    sha = context.partition_key
    snapshot_at = _get_commit_date(cfg, sha)

    pipeline = dlt.pipeline(
        pipeline_name=f"github_pipeline_{sha}",
        destination="postgres",
        dataset_name="public",
        progress="log",
    )
    load_info = pipeline.run(
        github_source(
            owner=cfg.owner,
            repo=cfg.repo,
            path=cfg.path,
            access_token=cfg.token,
            commit_sha=sha,
            branch=cfg.branch,
            snapshot_at=snapshot_at,
        )
    )
    context.log.info(
        f"Loaded sha={sha} snapshot_at={snapshot_at} packages={len(load_info.loads_ids)}"
    )
