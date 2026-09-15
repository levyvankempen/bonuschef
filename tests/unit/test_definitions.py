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
        "recipe_pool_refresh",
        "source_freshness",
    }


def test_markdowns_refresh_only_touches_clearance_lineage(defs, asset_graph):
    """Hourly, so it must stay narrow - but "narrow" means clearance's lineage,
    not a frozen list.

    The opportunity marts joined that lineage when they started reading
    clearance, and they belong in this job: the whole point of Vanavond is that
    at 17:30 it reflects the scrape that just ran, not last night's rebuild.
    They are small - the offer layer is a few hundred rows - so the hourly cost
    is negligible. What must never appear here is the GitHub feed or the recipe
    pool, which would turn an hourly job into a bulk load.
    """
    job = next(j for j in defs.jobs if j.name == "markdowns_refresh")
    keys = _keys(job, asset_graph)
    assert keys == {
        "ah__store_markdowns",
        "stg_ah__markdowns",
        "marts/fct_store_clearance",
        "marts/fct_store_clearance_history",
        "int_store",
        "int_product_offer_today",
        "int_recipe_item_opportunity",
        "marts/fct_recipe_opportunity",
        "marts/fct_recipe_opportunity_items",
    }
    assert "github__products" not in keys
    assert "ah__recipe_pool" not in keys


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
        "recipe_pool_refresh_schedule",
        "source_freshness_schedule",
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


def test_the_dbt_executable_is_resolved_absolutely():
    """DbtCliResource defaults to the bare name "dbt" and finds it through
    PATH. That held only while the containers started through `uv run`; it does
    not any more, and the failure mode was every code location refusing to
    load."""
    from bonuschef.dags.defs.resources.dbt import dbt

    assert dbt.dbt_executable != "dbt", "resolving through PATH is what broke"
    assert Path(dbt.dbt_executable).is_absolute()


def test_the_recipe_pool_stays_out_of_the_nightly_rebuild(defs, asset_graph):
    """daily_refresh_job selects everything except the "dlt" group. An asset
    outside that group would refetch the whole pool every night at 17:30, inside
    the dbt rebuild and against the only concurrency slot."""
    job = next(j for j in defs.jobs if j.name == "daily_refresh")
    assert "ah__recipe_pool" not in _keys(job, asset_graph)


def test_the_pool_refresh_runs_weekly_clear_of_everything_urgent(defs):
    """Three constraints pick 04:00 Monday, and each one matters."""
    schedule = next(
        s for s in defs.schedules if s.name == "recipe_pool_refresh_schedule"
    )
    minute, hour, _, _, weekday = schedule.cron_schedule.split()
    assert weekday != "*", "the pool is weekly; daily would be 7x the requests"
    hour_i = int(hour)
    # After the 03:30 heartbeat has already proven the credential, so a crawl is
    # never what discovers a dead one.
    assert hour_i >= 4
    # Outside 11:00-20:00, which is unbackfillable and has absolute priority.
    assert not (11 <= hour_i <= 20)
    assert schedule.execution_timezone == "Europe/Amsterdam"


def test_the_pool_refresh_does_not_retry_into_the_auth_chain(defs):
    """The pool is never urgent and the AH credential is the scarce thing.
    Retrying a rejected credential is how it gets burned."""
    job = next(j for j in defs.jobs if j.name == "recipe_pool_refresh")
    assert job.op_retry_policy is not None
    assert job.op_retry_policy.max_retries <= 1


def test_the_pool_refresh_also_proposes_products(defs, asset_graph):
    """A refreshed pool with no product matches ranks nothing.

    Fetching 900 recipes is the cheap half; knowing which product an ingredient
    can be bought as is what makes them rankable. A job that did the first and
    not the second would report success having achieved nothing.
    """
    job = next(j for j in defs.jobs if j.name == "recipe_pool_refresh")
    keys = _keys(job, asset_graph)
    assert "ah__recipe_pool" in keys
    assert "ah__ingredient_proposals" in keys


def test_the_proposal_step_is_not_in_the_credential_spending_group(defs, asset_graph):
    """group_name="dlt" exists to keep AH-spending assets out of the nightly
    rebuild. The matcher spends nothing - it is a local regex against
    dim_product - and should run whenever the catalogue moves, because a product
    that appeared today may resolve an ingredient that failed yesterday."""
    job = next(j for j in defs.jobs if j.name == "daily_refresh")
    keys = _keys(job, asset_graph)
    assert "ah__ingredient_proposals" in keys
    assert "ah__recipe_pool" not in keys


def test_the_refresh_a_person_waits_on_runs_in_process(defs):
    """The clearance refresh is the one job someone stands in a shop waiting on.

    Measured at 39s, of which the AH scrape was 1 second and dbt's actual work
    was 4. The rest was process spawning: the multiprocess executor starts a
    fresh subprocess per step, each re-importing dagster, dagster-dbt and the
    dbt manifest. Its two steps are strictly sequential - scrape, then rebuild
    what the scrape fed - so there is no parallelism to lose, and running them
    in one process took it to ~23s.
    """
    from dagster._core.definitions.executor_definition import in_process_executor

    job = next(j for j in defs.jobs if j.name == "markdowns_refresh")
    assert job.executor_def is in_process_executor, (
        "a subprocess per step doubles the wait on the only interactive job"
    )


def test_bulk_jobs_keep_process_isolation(defs):
    """The trade is deliberate and does not generalise. A long unattended batch
    wants a subprocess it can lose without taking the run with it; a button
    someone is waiting on does not."""
    from dagster._core.definitions.executor_definition import in_process_executor

    for name in ("github_products", "all_assets"):
        job = next((j for j in defs.jobs if j.name == name), None)
        if job is not None:
            assert job.executor_def is not in_process_executor, (
                f"{name} is a bulk job and should keep its isolation"
            )


def test_the_pool_is_refreshed_rather_than_accumulated():
    """merge upserts and never deletes, so a recipe that fell out of AH's
    listing stayed in the pool and kept being ranked - the opposite of the
    module's own docstring and of the binding requirement.

    Invisible today, because the pool has only ever been loaded from one
    enumeration. It becomes visible the first time AH's listing turns over: the
    pool grows past its stated bound, the honest count the portal must show
    starts overstating what is current, and the review queue lengthens with
    concepts from recipes nobody would be offered.
    """
    from pathlib import Path as _Path

    import bonuschef.dags.defs.assets.dlt.ah_recipe_pool as pool

    source = _Path(pool.__file__).read_text()
    body = source[source.index("def recipe_pool_source") :]
    assert 'write_disposition="merge"' not in body, (
        "merge leaves evicted recipes in the pool forever"
    )
    assert body.count('write_disposition="replace"') == 2, (
        "both resources must be replaced, or the ingredients outlive their recipes"
    )


def test_an_empty_fetch_cannot_truncate_a_good_pool():
    """What makes replace safe. Without it, a bad fetch would empty the pool
    rather than leaving the last good one serving."""
    from pathlib import Path as _Path

    import bonuschef.dags.defs.assets.dlt.ah_recipe_pool as pool

    source = _Path(pool.__file__).read_text()
    # The message is split across two source lines; match the half that
    # carries the meaning rather than a span that formatting can break.
    assert "an empty pool over a good one" in source
    guard = source.index("if not recipes:")
    write = source.index("pipeline.run(")
    assert guard < write, "the guard must precede the write it protects"


def test_eviction_cannot_reach_a_persons_own_recipes():
    """Adopted, hand-entered and kept recipes are not in the pool table at all -
    they live in portal-owned tables dbt reads and never writes. That is the
    property that makes truncating the pool a small change."""
    from pathlib import Path as _Path

    models = (
        _Path(__file__).resolve().parents[2] / "src" / "bonuschef" / "sql" / "models"
    )
    available = (
        models / "intermediate" / "recipes" / "int_pool_recipes_available.sql"
    ).read_text()
    assert "stg_portal__ah_recipes" in available, "adopted recipes stay exempt"
    assert "stg_portal__ah_recipe_verdicts" in available, "rejections outlive a refetch"
