"""Dagster sensors for discovering new data partitions."""

import requests
from dagster import (
    DagsterRunStatus,
    DefaultSensorStatus,
    RunRequest,
    RunStatusSensorContext,
    SensorEvaluationContext,
    SensorResult,
    run_failure_sensor,
    run_status_sensor,
    sensor,
)
from dagster import RunFailureSensorContext
from dagster._core.events import StepFailureData

from bonuschef.config import GitHubConfig, NtfyConfig
from bonuschef.dags.defs.assets.dlt.github import GITHUB_PARTITIONS
from bonuschef.dags.defs.jobs import backfill_job, dbt_job
from bonuschef.dags.defs.utils.github_commit_helper import commits_since_date


@sensor(
    minimum_interval_seconds=3600,
    job=backfill_job,
    default_status=DefaultSensorStatus.RUNNING,
)
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
        run_requests=[RunRequest(partition_key=sha) for sha in new_shas],
    )


@run_status_sensor(
    run_status=DagsterRunStatus.SUCCESS,
    monitored_jobs=[backfill_job],
    request_job=dbt_job,
    default_status=DefaultSensorStatus.RUNNING,
)
def dbt_after_backfill_sensor(context: RunStatusSensorContext):
    """Trigger dbt models after GitHub backfill job succeeds."""
    return RunRequest()


_NTFY_TIMEOUT_S = 10
_MAX_REASON_CHARS = 300


def _failure_reason(context: RunFailureSensorContext) -> str:
    """The text that makes an alert actionable.

    ``context.failure_event.message`` only says which steps failed, not why, so
    an alert built on it would tell you nothing you could act on. The actual
    exception — including the ``ah_login`` hint when a credential has died —
    lives on the step failure events.
    """
    for event in context.get_step_failure_events():
        data = event.event_specific_data
        # get_step_failure_events only yields STEP_FAILURE, but the event union
        # is wide and most of its members carry no error.
        error = data.error if isinstance(data, StepFailureData) else None
        if error is not None:
            # Dagster wraps a user exception in DagsterExecutionStepExecutionError,
            # whose own message is only "Error occurred while executing op ...".
            # The text worth paging someone about — including the ah_login hint
            # when a credential has died — is the innermost cause.
            while error.cause is not None:
                error = error.cause
            # .message, not .to_string(): the latter is a multi-kilobyte stack
            # trace and this is going to a phone notification.
            return f"{event.step_key}: {error.message.strip()}"[:_MAX_REASON_CHARS]
    return (context.failure_event.message or "run failed")[:_MAX_REASON_CHARS]


@run_failure_sensor(
    name="run_failure_alert_sensor",
    default_status=DefaultSensorStatus.RUNNING,
    description="Pushes unattended run failures to ntfy so they are seen in hours.",
)
def run_failure_alert_sensor(context: RunFailureSensorContext) -> None:
    """Notify on any failed run in this code location.

    Covers scheduled runs, the portal's on-demand refresh, and manual runs — a
    superset of what the spec requires, and the useful behaviour: a failure you
    triggered by hand is still a failure you want to know about.
    """
    cfg = NtfyConfig.from_env()
    if cfg is None:
        return  # alerting is opt-in; unconfigured is not an error

    run = context.dagster_run
    try:
        requests.post(
            cfg.url,
            data=f"{run.job_name} failed\n{_failure_reason(context)}".encode(),
            headers={"Title": f"bonuschef: {run.job_name}", "Priority": "high"},
            timeout=_NTFY_TIMEOUT_S,
        )
    except Exception as exc:
        # Never re-raise. A sensor that raises leaves the daemon's cursor
        # uncommitted, so the next tick reprocesses the same failure and
        # notifies again — catching is what makes "one notification" true.
        context.log.warning(
            "Could not deliver failure alert for %s: %s", run.run_id, exc
        )
