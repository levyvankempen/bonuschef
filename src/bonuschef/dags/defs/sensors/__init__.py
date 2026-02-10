"""Dagster sensors for discovering new data partitions."""

from dagster import (
    RunRequest,
    SensorEvaluationContext,
    SensorResult,
    sensor,
)

from bonuschef.config import GitHubConfig
from bonuschef.dags.defs.assets.dlt.github import GITHUB_PARTITIONS
from bonuschef.dags.defs.jobs import backfill_job
from bonuschef.dags.defs.utils.github_commit_helper import commits_since_date


@sensor(minimum_interval_seconds=3600, job=backfill_job)
def github_commit_sensor(context: SensorEvaluationContext) -> SensorResult:
    """Discover new GitHub commits and add them as dynamic partitions.

    Runs hourly, fetches commits matching the configured message filter,
    and triggers materialization for any newly discovered SHAs.
    """
    try:
        cfg = GitHubConfig.from_env()
    except ValueError as e:
        return SensorResult(skip_reason=f"Config error: {e}")

    commits = commits_since_date(
        owner=cfg.owner,
        repo=cfg.repo,
        message_filter=cfg.message_filter,
        since_iso_utc=cfg.start_date,
        branch=cfg.branch,
        token=cfg.token,
        max_pages=cfg.max_pages,
    )

    all_shas = [c["sha"] for c in commits]
    existing = set(context.instance.get_dynamic_partitions("github_commits"))
    new_shas = [sha for sha in all_shas if sha not in existing]

    if not new_shas:
        return SensorResult(skip_reason="No new commits found")

    context.log.info(f"Discovered {len(new_shas)} new commit(s)")

    return SensorResult(
        dynamic_partitions_requests=[
            GITHUB_PARTITIONS.build_add_request(new_shas),
        ],
        run_requests=[
            RunRequest(partition_key=sha) for sha in new_shas
        ],
    )
