"""Thin wrapper around the Dagster GraphQL API for on-demand job runs.

The portal never runs pipelines itself; it asks the Dagster webserver to
launch a job and then polls the run until it reaches a terminal state. That
keeps Dagster as the single place where runs are recorded and retried.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

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


# The two steps of markdowns_refresh, in order, with what each is doing in terms
# a person waiting on it would recognise. Phase is read from the run rather than
# estimated from elapsed time: a bar that advances on a timer is a decoration,
# and it would have said "almost done" through the three minutes a queued run
# spent doing nothing at all.
REFRESH_PHASES: tuple[tuple[str, str], ...] = (
    ("ah__store_markdowns", "De winkel wordt gescand…"),
    ("dbt_assets", "De prijzen worden bijgewerkt…"),
)


@dataclass(frozen=True)
class RunProgress:
    """Where a run has got to, as far as Dagster will say."""

    status: DagsterRunStatus
    label: str
    # Completed steps over total steps. Deliberately coarse: there are two, and
    # inventing finer granularity would mean inventing the numbers.
    completed: int
    total: int

    @property
    def fraction(self) -> float:
        return min(1.0, self.completed / self.total) if self.total else 0.0


_STEP_STATS_QUERY = """query RunProgress($id: ID!) {
  runOrError(runId: $id) {
    ... on Run { status stepStats { stepKey status } }
  }
}"""


def get_run_progress(
    run_id: str,
    phases: tuple[tuple[str, str], ...] = REFRESH_PHASES,
    cfg: DagsterConfig | None = None,
) -> RunProgress:
    """How far a run has got, phrased for someone waiting on it.

    Falls back to the run's own status when step stats are unavailable - during
    the first seconds a run exists there are no steps yet, and Dagster spends
    that time launching a process and importing the code location. Reporting
    "starten" then is honest; reporting a percentage would not be.
    """
    cfg = cfg or DagsterConfig.from_env()
    try:
        payload = _client(cfg)._execute(_STEP_STATS_QUERY, {"id": run_id})
    except Exception as exc:
        raise DagsterTriggerError(
            f"Could not read progress of run {run_id[:8]} from Dagster: {exc}"
        ) from exc

    node = (payload or {}).get("runOrError") or {}
    raw_status = node.get("status")
    if raw_status is None:
        raise DagsterTriggerError(f"Dagster does not know run {run_id[:8]}")
    status = DagsterRunStatus(raw_status)

    by_key = {s.get("stepKey"): s.get("status") for s in node.get("stepStats") or []}
    total = len(phases)

    if status == DagsterRunStatus.QUEUED:
        # Waiting is a normal state - runs are serialised instance-wide - and
        # calling it "scanning" is what once sent an hour of debugging at the
        # wrong component.
        return RunProgress(status, "In de wachtrij…", 0, total)
    if status in TERMINAL_STATUSES:
        done = (
            total
            if status == DagsterRunStatus.SUCCESS
            else len([v for v in by_key.values() if v == "SUCCESS"])
        )
        return RunProgress(status, "Klaar", done, total)

    completed = sum(1 for key, _ in phases if by_key.get(key) == "SUCCESS")
    for key, label in phases:
        state = by_key.get(key)
        if state in (None, "SKIPPED"):
            continue
        if state != "SUCCESS":
            return RunProgress(status, label, completed, total)
    if completed:
        return RunProgress(status, "Afronden…", completed, total)
    # A run exists but no step has started: Dagster is launching the process and
    # importing the code location, which is most of the wait.
    return RunProgress(status, "Starten…", 0, total)
