"""Prune Dagster's own history, which nothing else bounds.

dagster.yaml bounds schedule and sensor ticks. It cannot bound event_logs -
Dagster OSS has no retention setting for them - and its comment said to see
docs/deployment.md, where the word event_log does not appear. The pointer was
to a procedure nobody wrote.

The failure it describes is specific and worth repeating: the first symptom of
a filling disk is not a full disk, it is daily_refresh failing to spill its
temp files while the smaller hourly scrape keeps working. That reads as "the
recipe prices seem stuck", which is a long way from "the disk is full".

Deleting a run deletes its event logs with it, which is the supported way to
reclaim that space - reaching into the table directly would work until a
schema change made it not.
"""

from dagster import Config, OpExecutionContext, RetryPolicy, job, op

# Three months. Long enough that a question about last month's prices can still
# be answered from the run history, short enough that ~13 runs a day do not
# accumulate indefinitely on a 16 GB rootfs.
DEFAULT_KEEP_DAYS = 90


class RetentionConfig(Config):
    keep_days: int = DEFAULT_KEEP_DAYS


@op
def prune_run_history(context: OpExecutionContext, config: RetentionConfig) -> dict:
    """Delete runs, and therefore event logs, older than the window."""
    from datetime import datetime, timedelta, timezone

    from dagster import DagsterRunStatus, RunsFilter

    cutoff = datetime.now(timezone.utc) - timedelta(days=config.keep_days)

    # Filtered in storage rather than in Python: the instance can answer "older
    # than this, and finished" without handing back every run it holds, which
    # is the whole point of pruning.
    #
    # Finished only. Deleting a run that is still executing would remove the
    # record out from under the process writing it.
    old = context.instance.get_runs(
        filters=RunsFilter(
            created_before=cutoff,
            statuses=[
                DagsterRunStatus.SUCCESS,
                DagsterRunStatus.FAILURE,
                DagsterRunStatus.CANCELED,
            ],
        ),
        limit=5000,
    )

    for run in old:
        context.instance.delete_run(run.run_id)

    context.log.info(
        "Deleted %d run(s) older than %d days, and their event logs",
        len(old),
        config.keep_days,
    )
    return {"deleted": len(old), "keep_days": config.keep_days}


@job(
    name="prune_run_history",
    description="Delete Dagster runs, and their event logs, past the retention window.",
    # Every scheduled job here retries once, and a test enforces it: a prune
    # that gives up on a transient database hiccup waits a week for its next
    # chance.
    op_retry_policy=RetryPolicy(max_retries=1, delay=60),
)
def prune_run_history_job() -> None:
    prune_run_history()
