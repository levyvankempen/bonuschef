"""Evaluating the source freshness thresholds that are already declared.

Five sources declare `warn_after` / `error_after`. Nothing ran them: `dbt build`
does not check source freshness, and `dbt source freshness` appeared nowhere in
the repo. The comment above one of those declarations reads *"This feed went 69
days without loading and nothing reported it"* — which described the present,
not the past.

Deliberately its own job rather than a step inside the rebuild. A stale feed
must not fail the rebuild: the rebuild is exactly what you still want when a
feed is late, because it keeps the last good data serving.
"""

# No `from __future__ import annotations` here: it stringifies the context
# annotation and Dagster then refuses the op with "Cannot annotate `context`
# parameter with type OpExecutionContext". Python 3.12 needs it for nothing in
# this file anyway.
import json
from pathlib import Path

from dagster import OpExecutionContext, RetryPolicy, job, op

from bonuschef.dags.defs.resources.dbt import dbt as dbt_resource

_PROJECT_DIR = Path(dbt_resource.project_dir)


def _states(results_path: Path) -> list[tuple[str, str, float | None]]:
    """(source name, state, age in seconds) for each source dbt evaluated."""
    if not results_path.exists():
        return []
    payload = json.loads(results_path.read_text())
    out: list[tuple[str, str, float | None]] = []
    for row in payload.get("results", []):
        name = ".".join(row.get("unique_id", "").split(".")[-2:]) or "?"
        criteria = row.get("criteria") or {}
        max_loaded = row.get("max_loaded_at_time_ago_in_s")
        # A source dbt could not time is not fresh. It has no loaded_at it
        # could read, which is the same evidential position as never loading.
        state = row.get("status", "error")
        if max_loaded is None and state == "pass" and criteria:
            state = "error"
        out.append((name, state, max_loaded))
    return out


@op(description="Evaluate the declared source freshness thresholds.")
def check_source_freshness(context: OpExecutionContext) -> None:
    from dagster_dbt import DbtCliResource

    dbt = DbtCliResource(
        project_dir=str(_PROJECT_DIR), dbt_executable=dbt_resource.dbt_executable
    )
    # raise_on_error=False: dbt exits non-zero for a stale source, and we want
    # to read which source and report it rather than surfacing an exit code.
    invocation = dbt.cli(["source", "freshness"], raise_on_error=False)
    list(invocation.stream_raw_events())

    # dagster-dbt gives every invocation its own target directory so concurrent
    # runs cannot clobber each other's artifacts, so sources.json is NOT in
    # target/. Reading the path from the invocation rather than assuming it is
    # the difference between this check working and reporting "no results" -
    # which it did, on the first live run.
    states = _states(Path(invocation.target_path) / "sources.json")
    if not states:
        raise RuntimeError(
            "dbt produced no freshness results. Either no source declares a "
            "threshold any more, or the run did not complete - both mean this "
            "check is no longer checking anything."
        )

    stale = [(n, s, a) for n, s, a in states if s == "error"]
    warned = [(n, s, a) for n, s, a in states if s == "warn"]

    for name, _, age in warned:
        context.log.warning(
            "%s is behind its warn threshold (%s hours old)",
            name,
            "unknown" if age is None else round(age / 3600, 1),
        )
    context.add_output_metadata(
        {
            "sources_checked": len(states),
            "stale": len(stale),
            "warned": len(warned),
        }
    )
    if stale:
        detail = ", ".join(
            f"{n} ({'unknown' if a is None else round(a / 3600, 1)}h old)"
            for n, _, a in stale
        )
        # Fail the run. A stale feed that reports success is the state this
        # whole check exists to end.
        raise RuntimeError(
            f"{len(stale)} source(s) past their error threshold: {detail}. "
            "The marts built from them are describing a past that has moved."
        )


@job(
    name="source_freshness",
    description="Report sources that have stopped arriving.",
    # One retry, at the job level like every other scheduled job. A stale feed
    # will not have become fresh 60 seconds later - this is for the transient
    # case, a dbt invocation losing its Postgres connection, which would
    # otherwise report a freshness failure that is really a connection failure.
    op_retry_policy=RetryPolicy(max_retries=1, delay=60),
)
def source_freshness_job() -> None:
    check_source_freshness()
