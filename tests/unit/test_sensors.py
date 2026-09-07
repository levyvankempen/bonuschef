"""Tests for Dagster sensors using an ephemeral instance."""

import pytest
from dagster import DagsterInstance, SensorResult, build_sensor_context

from bonuschef.dags.defs import sensors as sensors_module
from bonuschef.dags.defs.sensors import github_commit_sensor

GITHUB_ENV = {
    "GITHUB_OWNER": "supermarkt",
    "GITHUB_REPO": "checkjebon",
    "GITHUB_PATH": "data/supermarkets.json",
    "GITHUB_MESSAGE_FILTER": "Update supermarkets.json",
    "GITHUB_START_DATE": "2025-01-01T00:00:00Z",
    "GITHUB_BRANCH": "main",
    "GITHUB_MAX_PAGES": "2",
}


@pytest.fixture
def github_env(monkeypatch):
    for key, value in GITHUB_ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def instance():
    with DagsterInstance.ephemeral() as inst:
        yield inst


def _evaluate(instance) -> SensorResult:
    context = build_sensor_context(instance=instance)
    result = github_commit_sensor(context)
    assert isinstance(result, SensorResult)
    return result


def test_config_error_skips(monkeypatch, instance):
    monkeypatch.delenv("GITHUB_MAX_PAGES", raising=False)
    result = _evaluate(instance)
    assert result.skip_reason is not None
    assert "Config error" in str(result.skip_reason)


def test_new_commits_become_partitions_and_runs(monkeypatch, instance, github_env):
    monkeypatch.setattr(
        sensors_module,
        "commits_since_date",
        lambda **kw: [{"sha": "aaa"}, {"sha": "bbb"}],
    )
    result = _evaluate(instance)
    assert result.skip_reason is None
    (req,) = result.dynamic_partitions_requests
    assert req.partitions_def_name == "github_commits"
    assert list(req.partition_keys) == ["aaa", "bbb"]
    assert [r.partition_key for r in result.run_requests] == ["aaa", "bbb"]


def test_known_partitions_are_not_rerun(monkeypatch, instance, github_env):
    instance.add_dynamic_partitions("github_commits", ["aaa"])
    monkeypatch.setattr(
        sensors_module,
        "commits_since_date",
        lambda **kw: [{"sha": "aaa"}, {"sha": "ccc"}],
    )
    result = _evaluate(instance)
    assert [r.partition_key for r in result.run_requests] == ["ccc"]


def test_nothing_new_skips(monkeypatch, instance, github_env):
    instance.add_dynamic_partitions("github_commits", ["aaa"])
    monkeypatch.setattr(
        sensors_module, "commits_since_date", lambda **kw: [{"sha": "aaa"}]
    )
    result = _evaluate(instance)
    assert "No new commits" in str(result.skip_reason)


def test_sensor_forwards_config(monkeypatch, instance, github_env):
    captured = {}

    def fake(**kw):
        captured.update(kw)
        return []

    monkeypatch.setattr(sensors_module, "commits_since_date", fake)
    _evaluate(instance)
    assert captured["owner"] == "supermarkt"
    assert captured["max_pages"] == 2
    assert captured["since_iso_utc"] == "2025-01-01T00:00:00Z"
