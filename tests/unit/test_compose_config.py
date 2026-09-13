"""Deployment guarantees, asserted by reading the tracked config files.

These run without Docker: the stack's promises for an unattended host - it
restarts itself, it cannot fill the disk, it answers on loopback only, it
reports its health, and its instance config actually reaches the container -
are all data in ``docker-compose.yml`` and ``dagster.yaml``. Parsing them keeps
the check in the normal test run, and every per-service rule is asserted by
iterating ``services`` so a service added later is covered too.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
DAGSTER_FILE = REPO_ROOT / "dagster.yaml"
ENV_EXAMPLE = REPO_ROOT / ".env.example"

# Services that serve HTTP and therefore must report health. dagster-daemon is
# absent by design (no port to poll); this is deliberately not asserted as an
# absence, so adding `dagster-daemon liveness-check` later stays legal.
WEB_SERVICES = {
    "dagster-webserver": "/server_info",
    "streamlit": "/_stcore/health",
}
DAGSTER_SERVICES = ("dagster-webserver", "dagster-daemon")


@pytest.fixture(scope="module")
def compose() -> dict[str, Any]:
    return yaml.safe_load(COMPOSE_FILE.read_text())


@pytest.fixture(scope="module")
def services(compose: dict[str, Any]) -> dict[str, Any]:
    return compose["services"]


@pytest.fixture(scope="module")
def dagster_instance() -> dict[str, Any]:
    return yaml.safe_load(DAGSTER_FILE.read_text())


def test_the_expected_services_are_defined(services):
    assert set(services) == {
        "postgres",
        "dagster-webserver",
        "dagster-daemon",
        "streamlit",
    }


# --- recovery, logs, exposure: asserted for every service ------------------


def test_every_service_restarts_unless_stopped(services):
    """Reboot recovery. `always` would also undo a deliberate `compose stop`."""
    for name, svc in services.items():
        assert svc.get("restart") == "unless-stopped", f"{name} has no restart policy"


def test_every_service_bounds_its_own_logs(services):
    for name, svc in services.items():
        logging = svc.get("logging")
        assert logging, f"{name} has no logging options; its logs grow forever"
        assert logging["driver"] == "json-file", name
        options = logging["options"]
        assert options.get("max-size"), f"{name} does not cap log file size"
        assert options.get("max-file"), f"{name} does not cap rotated log count"


def test_every_published_port_binds_to_loopback(services):
    """Neither web UI authenticates, and Dagster's can start and kill jobs."""
    published = [
        (name, mapping)
        for name, svc in services.items()
        for mapping in svc.get("ports", [])
    ]
    assert published, "expected at least one published port"
    for name, mapping in published:
        assert str(mapping).startswith("127.0.0.1:"), (
            f"{name} publishes {mapping} on every interface"
        )


def test_no_service_ships_a_working_default_password(services):
    """A missing secret must fail startup, not fall back to a known value."""
    for name, svc in services.items():
        for key, value in (svc.get("environment") or {}).items():
            if "PASSWORD" in key.upper():
                assert str(value).startswith("${"), (
                    f"{name} hardcodes {key} instead of reading it from the environment"
                )


# --- health reporting -------------------------------------------------------


@pytest.mark.parametrize(("service", "path"), sorted(WEB_SERVICES.items()))
def test_web_services_report_health(services, service: str, path: str):
    healthcheck = services[service].get("healthcheck")
    assert healthcheck, f"{service} serves HTTP but reports no health"

    test = healthcheck["test"]
    # Exec form (CMD, not CMD-SHELL): no shell means no quoting hazard in the
    # embedded Python, where a typo would leave the container permanently
    # unhealthy.
    assert test[0] == "CMD", f"{service} should use the exec form"
    assert test[1] == "python", f"{service} probe should call the interpreter directly"
    probe = " ".join(test)
    assert path in probe, f"{service} does not poll {path}"
    # localhost can resolve ::1 first and pay a failed connect; both servers
    # bind IPv4 only.
    assert "127.0.0.1" in probe and "localhost" not in probe, service
    # `uv run` would re-resolve the environment and lock .venv on every probe.
    assert "uv" not in test[:2], f"{service} probe must not go through uv run"

    for field in ("interval", "timeout", "retries", "start_period"):
        assert healthcheck.get(field), f"{service} healthcheck has no {field}"


# --- instance config actually reaching the container ------------------------


@pytest.mark.parametrize("service", DAGSTER_SERVICES)
def test_dagster_yaml_is_bind_mounted(services, service: str):
    """The dagster_home named volume masks the copy the image puts there, so
    without this mount every edit to dagster.yaml silently never applies."""
    mounts = services[service]["volumes"]
    assert "./dagster.yaml:/app/dagster_home/dagster.yaml:ro" in mounts, (
        f"{service} would run a stale dagster.yaml from its named volume"
    )


def test_runs_are_serialised(dagster_instance):
    """daily_refresh rebuilds every dbt model, a superset of what
    markdowns_refresh touches; concurrent dbt against one Postgres races on
    on-run-start DDL and on table materialisation. Dagster's default is 10."""
    config = dagster_instance["run_coordinator"]["config"]
    assert config["max_concurrent_runs"] == 1


def test_dagster_storage_is_postgres_not_sqlite(dagster_instance):
    storage = dagster_instance.get("storage")
    assert storage, "storage defaults to SQLite on the shared dagster_home volume"
    assert "postgres" in storage
    assert "sqlite" not in yaml.dump(storage).lower()


# --- a deployment can be configured from the repo alone ---------------------


def test_env_example_covers_every_interpolated_variable(compose):
    """`docker compose up` fails on a missing ${VAR}; the template must list it."""
    referenced = {
        match.group(1)
        for match in re.finditer(r"\$\{([A-Z_][A-Z0-9_]*)", COMPOSE_FILE.read_text())
    }
    documented = {
        line.split("=", 1)[0].strip()
        for line in ENV_EXAMPLE.read_text().splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    assert referenced <= documented, (
        f"undocumented in .env.example: {sorted(referenced - documented)}"
    )


def test_env_example_documents_the_variables_the_services_read(services):
    """env_file keys are not interpolated, so they need their own check."""
    documented = {
        line.split("=", 1)[0].strip()
        for line in ENV_EXAMPLE.read_text().splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    for required in (
        "PG_USER",
        "PG_PASSWORD",
        "PG_DB",
        "AH_REFRESH_TOKEN",
        "NTFY_TOPIC",
        "NTFY_SERVER",
    ):
        assert required in documented, f"{required} missing from .env.example"


def test_env_example_carries_no_real_secret():
    text = ENV_EXAMPLE.read_text()
    assert "ghp_xxxx" in text or "GITHUB_TOKEN=" in text
    for line in text.splitlines():
        if line.startswith("AH_REFRESH_TOKEN="):
            assert len(line.split("=", 1)[1]) < 40, "looks like a real token"


def test_runs_stay_serialised_but_a_wedged_run_is_bounded(dagster_instance):
    """max_concurrent_runs: 1 alone is a trap: a wedged run holds the only slot,
    every queued run waits forever including the token heartbeat, and a QUEUED
    run emits no RUN_FAILURE - so the alerting would stay silent."""
    assert dagster_instance["run_coordinator"]["config"]["max_concurrent_runs"] == 1
    monitoring = dagster_instance.get("run_monitoring")
    assert monitoring, "a wedged run could starve the heartbeat indefinitely"
    assert monitoring["enabled"] is True
    assert monitoring["max_runtime_seconds"] > 0


def test_run_level_retries_stay_unset(dagster_instance):
    """Run-level retries emit one RUN_FAILURE per attempt, which would turn one
    broken pipeline into N phone notifications. Retries belong on the jobs."""
    assert "run_retries" not in dagster_instance


def test_the_theme_reaches_the_container():
    """The Dockerfile bakes src/ into the image. A theme left out of the COPY
    would silently fall back to Streamlit's stock look with no error anywhere."""
    dockerfile = (REPO_ROOT / "Dockerfile").read_text()
    assert "COPY .streamlit/" in dockerfile

    ignore = REPO_ROOT / ".dockerignore"
    if ignore.exists():
        patterns = [
            line.strip()
            for line in ignore.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
        assert not any(p.rstrip("/") == ".streamlit" for p in patterns)


def test_the_theme_is_a_complete_palette():
    """A half-set theme is worse than none: Streamlit fills the gaps from its
    own defaults, so the page ends up part cookbook, part dev tool."""
    import tomllib

    theme = tomllib.loads((REPO_ROOT / ".streamlit" / "config.toml").read_text())["theme"]
    for key in (
        "base",
        "backgroundColor",
        "secondaryBackgroundColor",
        "textColor",
        "primaryColor",
        # Stock #ff4b4b / #ffa421 are the loudest "Streamlit app" tell, and they
        # are what the clearance urgency badges would use.
        "greenColor",
        "orangeColor",
        "redColor",
    ):
        assert theme.get(key), f"{key} not set; Streamlit would use its default"
    assert theme["chartCategoricalColors"], "charts would render Vega default blue"
