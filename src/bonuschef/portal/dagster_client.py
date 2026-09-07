"""Thin wrapper around the Dagster GraphQL API for on-demand job runs.

The portal never runs pipelines itself; it asks the Dagster webserver to
launch a job and then polls the run until it reaches a terminal state. That
keeps Dagster as the single place where runs are recorded and retried.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from dagster import DagsterRunStatus
from dagster_graphql import DagsterGraphQLClient

from bonuschef.config import DagsterConfig

MARKDOWNS_REFRESH_JOB = "markdowns_refresh"

TERMINAL_STATUSES = frozenset(
    {
        DagsterRunStatus.SUCCESS,
        DagsterRunStatus.FAILURE,
        DagsterRunStatus.CANCELED,
    }
)


class DagsterTriggerError(RuntimeError):
    """Raised when the Dagster webserver cannot be reached or rejects a request."""


def _client(cfg: DagsterConfig | None = None) -> DagsterGraphQLClient:
    cfg = cfg or DagsterConfig.from_env()
    return DagsterGraphQLClient(cfg.host, port_number=cfg.port, timeout=30)


def trigger_job(job_name: str, cfg: DagsterConfig | None = None) -> str:
    """Submit a run of ``job_name`` and return its run id."""
    try:
        return _client(cfg).submit_job_execution(job_name)
    except Exception as exc:  # gql/requests raise a zoo of transport errors
        raise DagsterTriggerError(
            f"Could not start job {job_name!r} via Dagster: {exc}"
        ) from exc


def get_run_status(run_id: str, cfg: DagsterConfig | None = None) -> DagsterRunStatus:
    """Return the current status of a Dagster run."""
    try:
        return _client(cfg).get_run_status(run_id)
    except Exception as exc:
        raise DagsterTriggerError(
            f"Could not read status of run {run_id[:8]} from Dagster: {exc}"
        ) from exc


def wait_for_run(
    run_id: str,
    timeout_s: float = 180,
    poll_s: float = 3,
    cfg: DagsterConfig | None = None,
    *,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> DagsterRunStatus:
    """Poll a run until it finishes or ``timeout_s`` elapses.

    Returns the last observed status, which is non-terminal on timeout so the
    caller can tell "still running" apart from "finished".
    """
    deadline = clock() + timeout_s
    while True:
        status = get_run_status(run_id, cfg)
        if status in TERMINAL_STATUSES or clock() >= deadline:
            return status
        sleep(poll_s)
