"""What grows, and what the probes actually check.

Both findings here are the same shape: something the project had already
identified in a comment, and then not done.
"""

from __future__ import annotations

import ast
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DAGSTER_YAML = ROOT / "dagster.yaml"
COMPOSE = ROOT / "docker-compose.yml"
DOCS = ROOT / "docs" / "deployment.md"


def test_event_logs_have_something_that_prunes_them():
    """dagster.yaml bounds schedule and sensor ticks and says event_logs "need
    pruning outside it - see docs/deployment.md".

    The word event_log appeared nowhere in that document. The pointer was to a
    procedure nobody wrote, for the table the same comment identifies as the
    fastest-growing thing on the disk.
    """
    from bonuschef.dags.defs.jobs.retention import prune_run_history_job

    assert prune_run_history_job is not None

    from bonuschef.dags import definitions

    names = {j.name for j in definitions.defs.jobs or []}
    assert "prune_run_history" in names, "the job exists but nothing can run it"


def test_the_prune_is_scheduled():
    """An unscheduled prune is the same as the docs section that did not
    exist: a thing that would work if anyone ran it."""
    from bonuschef.dags import definitions

    crons = {
        s.name: getattr(s, "cron_schedule", None)
        for s in definitions.defs.schedules or []
    }
    assert any("prune" in name for name in crons), crons


def test_the_prune_deletes_runs_rather_than_rows():
    """Deleting a run deletes its event logs with it, which is the supported
    path. Reaching into the table would work until a schema change made it
    not."""
    source = (
        ROOT / "src" / "bonuschef" / "dags" / "defs" / "jobs" / "retention.py"
    ).read_text()
    assert "instance.delete_run" in source
    assert "DELETE FROM" not in source.upper()


def test_the_prune_leaves_running_runs_alone():
    """Deleting a run still executing removes the record out from under the
    process writing it."""
    source = (
        ROOT / "src" / "bonuschef" / "dags" / "defs" / "jobs" / "retention.py"
    ).read_text()
    tree = ast.parse(source)
    text = ast.get_source_segment(source, tree) or source
    assert "SUCCESS" in text and "FAILURE" in text, (
        "the prune does not restrict itself to finished runs"
    )


def test_the_streamlit_probe_checks_more_than_the_server():
    """/_stcore/health answers for the server, not the app. docs/deployment.md
    records it returning 200 with a raise in app.py - a probe that passes
    while the service cannot do its job."""
    compose = yaml.safe_load(COMPOSE.read_text())
    test = compose["services"]["streamlit"]["healthcheck"]["test"]
    body = " ".join(test) if isinstance(test, list) else str(test)
    assert "_stcore/health" in body, "the server check was dropped entirely"
    assert "app_health" in body, (
        "the probe still asks only whether Streamlit is listening"
    )


def test_the_readiness_check_never_raises():
    """It runs inside a health probe. An exception there is a container
    marked unhealthy for the wrong reason."""
    from bonuschef.portal import app_health

    assert app_health.ready() in (True, False)


def test_the_readiness_check_reports_a_dead_warehouse(monkeypatch):
    from bonuschef.portal import app_health, db

    def _boom():
        raise RuntimeError("no database")

    monkeypatch.setattr(db, "get_engine", _boom)
    assert app_health.ready() is False
