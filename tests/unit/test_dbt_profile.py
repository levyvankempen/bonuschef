"""The dbt connection profile.

Build parallelism is measured, not guessed: on the full 20-model build one
thread takes 17.5s, two 10.6s, four 8.0s, six 6.8s, eight nothing more. Postgres
does the same ~21 CPU-seconds of work whichever it is, so on a 2 vCPU host that
floors the build near 10.5s and two threads already reach it.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

PROFILE = (
    Path(__file__).resolve().parents[2] / "src" / "bonuschef" / "sql" / "profiles.yml"
)


def _default_target() -> dict:
    profile = yaml.safe_load(PROFILE.read_text())
    return profile["dbt_bonuschef"]["outputs"]["default"]


def _default_thread_count() -> int:
    threads = str(_default_target()["threads"])
    match = re.search(r"env_var\(\s*'DBT_THREADS'\s*,\s*'(\d+)'\s*\)", threads)
    assert match is not None, f"threads should read DBT_THREADS, got {threads!r}"
    return int(match.group(1))


def test_models_do_not_build_one_at_a_time():
    """threads: 1 serialises all 20 models for no reason; the DAG is six wide
    at the staging layer alone."""
    assert _default_thread_count() > 1, "serial builds again"


def test_parallelism_stays_within_a_small_host():
    """More threads than cores buys queueing, not throughput, and multiplies
    concurrent temp-file pressure - each build already spills ~2.8 GB."""
    count = _default_thread_count()
    assert count <= 4, f"{count} threads oversubscribes a 2 vCPU host"


def test_threads_is_configurable_per_host():
    """One profile serves the dev machine and the VM; the number that suits a
    10-core laptop is not the one that suits 2 vCPU."""
    assert "env_var" in str(_default_target()["threads"])
