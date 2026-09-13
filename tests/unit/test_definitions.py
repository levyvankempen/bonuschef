"""Smoke tests for the Dagster code location: jobs, schedules, sensors resolve."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from dagster import AssetKey, DefaultScheduleStatus, DefaultSensorStatus

SQL_DIR = Path(__file__).resolve().parents[2] / "src" / "bonuschef" / "sql"
MANIFEST = SQL_DIR / "target" / "manifest.json"


def _ensure_manifest() -> None:
    """The dbt assets need a parsed manifest; build it once if absent (no DB needed)."""
    if MANIFEST.exists():
        return
    dbt = shutil.which("dbt")
    if dbt is None:
        # ty cannot see through pytest's @_with_exception decorator, so it
        # reads skip() as taking no arguments. Upstream limitation, not ours.
        pytest.skip("dbt CLI not on PATH and no manifest present")  # ty: ignore[too-many-positional-arguments]
    env = {**os.environ, "ENVIRONMENT": "default"}
    common = ["--project-dir", str(SQL_DIR), "--profiles-dir", str(SQL_DIR)]
    subprocess.run([dbt, "deps", *common], check=True, env=env, timeout=300)
    subprocess.run([dbt, "parse", *common], check=True, env=env, timeout=300)


@pytest.fixture(scope="module")
def defs():
    _ensure_manifest()
    os.environ.setdefault("ENVIRONMENT", "default")
    from bonuschef.dags.definitions import defs as definitions

    return definitions


@pytest.fixture(scope="module")
def asset_graph(defs):
    return defs.resolve_asset_graph()


def _keys(job, asset_graph) -> set[str]:
    return {k.to_user_string() for k in job.selection.resolve(asset_graph)}


def test_all_jobs_registered(defs):
    names = {job.name for job in defs.jobs}
    assert names == {
        "all_assets",
        "github_products",
        "dbt_models",
        "daily_refresh",
        "markdowns_refresh",
        "token_heartbeat",
        "recipes_rebuild",
    }


def test_markdowns_refresh_only_touches_clearance_lineage(defs, asset_graph):
    job = next(j for j in defs.jobs if j.name == "markdowns_refresh")
    keys = _keys(job, asset_graph)
    assert keys == {
        "ah__store_markdowns",
        "stg_ah__markdowns",
        "marts/fct_store_clearance",
        "marts/fct_store_clearance_history",
    }


def test_dbt_models_job_excludes_dlt_sources(defs, asset_graph):
    job = next(j for j in defs.jobs if j.name == "dbt_models")
    keys = _keys(job, asset_graph)
    assert "marts/fct_products" in keys
    assert not {"github__products", "ah__bonus_products", "ah__store_markdowns"} & keys


def test_daily_refresh_includes_bonus_feed_and_all_dbt(defs, asset_graph):
    job = next(j for j in defs.jobs if j.name == "daily_refresh")
    keys = _keys(job, asset_graph)
    assert "ah__bonus_products" in keys
    assert "marts/fct_recipe_cost_latest" in keys
    assert "github__products" not in keys


def test_schedules_run_in_amsterdam_time(defs):
    by_name = {s.name: s for s in defs.schedules}
    assert set(by_name) == {
        "daily_refresh_schedule",
        "markdowns_refresh_schedule",
        "token_heartbeat_schedule",
    }
    assert all(s.execution_timezone == "Europe/Amsterdam" for s in by_name.values())
    assert by_name["daily_refresh_schedule"].cron_schedule == "30 17 * * *"
    # Clearance deepens through the day; the hourly sequence is what makes the
    # markdown curve, so it stays independent of when the daily refresh runs.
    assert by_name["markdowns_refresh_schedule"].cron_schedule == "0 11-20 * * *"
    # Deliberately off the :00 scrapes and the 17:30 rebuild, and clear of the
    # 02:00-03:00 window that does not exist on the spring-forward day.
    assert by_name["token_heartbeat_schedule"].cron_schedule == "30 3,15 * * *"


def test_schedules_and_sensors_are_running_on_a_fresh_deployment(defs):
    """A new host has no stored scheduler state, so default_status decides
    whether anything runs at all. A paused schedule fails silently."""
    for schedule in defs.schedules:
        assert schedule.default_status == DefaultScheduleStatus.RUNNING, schedule.name
    for sensor in defs.sensors:
        assert sensor.default_status == DefaultSensorStatus.RUNNING, sensor.name


def test_scheduled_jobs_retry_transient_failures(defs):
    """Runs are serialised instance-wide (dagster.yaml), so a scheduled job can
    find the warehouse busy; without a retry it silently skips its slot."""
    by_name = {job.name: job for job in defs.jobs}
    # Every job a schedule targets, rather than a hardcoded list - otherwise the
    # next scheduled job silently reopens this gap.
    scheduled = {schedule.job_name for schedule in defs.schedules}
    assert scheduled, "expected at least one scheduled job"
    for name in scheduled:
        policy = by_name[name].op_retry_policy
        assert policy is not None, f"{name} gives up on the first failure"
        assert policy.max_retries >= 1


def test_sensors_registered(defs):
    assert {s.name for s in defs.sensors} == {
        "github_commit_sensor",
        "dbt_after_backfill_sensor",
        "run_failure_alert_sensor",
    }


def test_github_products_is_partitioned_by_commit(asset_graph):
    node = asset_graph.get(AssetKey("github__products"))
    assert node.partitions_def is not None
    assert node.partitions_def.name == "github_commits"


def test_heartbeat_runs_more_than_once_a_day(defs):
    """Pins the cadence decision: twice daily means one missed cycle still
    leaves same-day coverage.

    Deliberately not asserted against MAX_ACCESS_TOKEN_AGE_S - that is a local
    cap on the *access* token and says nothing about how long the *refresh*
    credential survives unused, which is the thing this schedule guards and
    whose value is exactly what the instrumentation exists to discover.
    """
    schedule = next(s for s in defs.schedules if s.name == "token_heartbeat_schedule")
    _, hours, *_ = schedule.cron_schedule.split()
    runs_per_day = len(hours.split(","))
    assert runs_per_day >= 2, "a single daily run has no margin for a missed cycle"
    assert 86_400 / runs_per_day <= 12 * 3600
