"""Smoke tests for the Dagster code location: jobs, schedules, sensors resolve."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from dagster import AssetKey

SQL_DIR = Path(__file__).resolve().parents[2] / "src" / "bonuschef" / "sql"
MANIFEST = SQL_DIR / "target" / "manifest.json"


def _ensure_manifest() -> None:
    """The dbt assets need a parsed manifest; build it once if absent (no DB needed)."""
    if MANIFEST.exists():
        return
    dbt = shutil.which("dbt")
    if dbt is None:
        pytest.skip("dbt CLI not on PATH and no manifest present")
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
    assert set(by_name) == {"daily_refresh_schedule", "markdowns_refresh_schedule"}
    assert all(s.execution_timezone == "Europe/Amsterdam" for s in by_name.values())
    assert by_name["daily_refresh_schedule"].cron_schedule == "0 6 * * *"
    assert by_name["markdowns_refresh_schedule"].cron_schedule == "0 11-20 * * *"


def test_sensors_registered(defs):
    assert {s.name for s in defs.sensors} == {
        "github_commit_sensor",
        "dbt_after_backfill_sensor",
    }


def test_github_products_is_partitioned_by_commit(asset_graph):
    node = asset_graph.get(AssetKey("github__products"))
    assert node.partitions_def is not None
    assert node.partitions_def.name == "github_commits"
