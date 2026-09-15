"""The freshness thresholds were declared for months and evaluated never.

Five sources carry warn_after/error_after. Nothing ran them: `dbt build` does
not check source freshness and `dbt source freshness` appeared nowhere. The
comment above one declaration - "This feed went 69 days without loading and
nothing reported it" - described the present rather than the past.
"""

import json

import yaml
from pathlib import Path

from bonuschef.dags.defs.jobs.freshness import _states

SQL = Path(__file__).resolve().parents[2] / "src" / "bonuschef" / "sql"


def _results(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "sources.json"
    p.write_text(json.dumps({"results": rows}))
    return p


def _row(name: str, status: str, age: float | None = 3600.0, criteria=True) -> dict:
    return {
        "unique_id": f"source.bonuschef.ah.{name}",
        "status": status,
        "max_loaded_at_time_ago_in_s": age,
        "criteria": {"warn_after": {"count": 3, "period": "hour"}} if criteria else {},
    }


class TestReadingDbtsVerdict:
    def test_a_passing_source_is_fresh(self, tmp_path):
        states = _states(_results(tmp_path, [_row("store_markdowns", "pass")]))
        assert [s for _, s, _ in states] == ["pass"]

    def test_a_stale_source_is_reported_as_error(self, tmp_path):
        states = _states(
            _results(tmp_path, [_row("bonus_products", "error", 999999.0)])
        )
        assert [s for _, s, _ in states] == ["error"]

    def test_a_source_dbt_could_not_time_is_not_fresh(self, tmp_path):
        """No loaded_at is the same evidential position as never having loaded.
        Treating it as a pass is how a feed goes 69 days unreported."""
        states = _states(_results(tmp_path, [_row("pool_recipes", "pass", None)]))
        assert [s for _, s, _ in states] == ["error"]

    def test_a_source_with_no_criteria_is_left_alone(self, tmp_path):
        """A source that declares no threshold is not being judged, so an
        absent timestamp says nothing about it."""
        states = _states(_results(tmp_path, [_row("x", "pass", None, criteria=False)]))
        assert [s for _, s, _ in states] == ["pass"]

    def test_no_results_file_yields_nothing(self, tmp_path):
        assert _states(tmp_path / "absent.json") == []


class TestTheDeclarationsThemselves:
    """The op fails when dbt reports nothing, because a check that checks
    nothing passes silently. These assert there is something to check."""

    def test_every_source_that_loads_on_a_cadence_declares_freshness(self):
        declared = {}
        for f in (SQL / "models" / "staging").rglob("_*sources.yml"):
            for src in yaml.safe_load(f.read_text()).get("sources", []):
                for table in src.get("tables", []):
                    if table.get("freshness"):
                        declared[f"{src['name']}.{table['name']}"] = table["freshness"]
        assert len(declared) >= 5, f"only {len(declared)} sources declare freshness"

    def test_each_source_is_judged_on_its_own_cadence(self):
        """An hourly scrape and a weekly snapshot held to one threshold means
        the weekly one is always stale or the hourly one never is."""
        windows = set()
        for f in (SQL / "models" / "staging").rglob("_*sources.yml"):
            for src in yaml.safe_load(f.read_text()).get("sources", []):
                for table in src.get("tables", []):
                    fr = table.get("freshness")
                    if fr and fr.get("warn_after"):
                        w = fr["warn_after"]
                        windows.add((w["count"], w["period"]))
        assert len(windows) > 1, "every source shares one threshold"

    def test_the_check_runs_on_a_schedule(self):
        """A threshold nothing evaluates is a comment."""
        from bonuschef.dags.defs.schedules import source_freshness_schedule

        assert source_freshness_schedule.job_name == "source_freshness"
        assert source_freshness_schedule.execution_timezone == "Europe/Amsterdam"

    def test_freshness_does_not_gate_the_rebuild(self):
        """A stale feed must not fail the rebuild - the rebuild is what keeps
        the last good data serving while the feed is late."""
        from bonuschef.dags.defs.jobs import source_freshness_job

        assert source_freshness_job.name == "source_freshness"
        # It stands alone; nothing else depends on it having passed.
        assert len(source_freshness_job.graph.node_defs) == 1
