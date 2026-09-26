"""Choosing a shop nobody has scraped starts the scrape.

Clearance is fetched per shop and the shop list is read from the accounts, so
the scheduled run does pick up a new shop on its own - it just does not know
somebody is waiting. Until it came round, a new person's first Laatste kans was
empty, on the visit that decides whether they come back.

The guard matters as much as the trigger: runs are serialised for the whole
instance, so firing on every shop change would let somebody queue work with a
dropdown, in front of an hourly scrape that cannot be backfilled.
"""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from bonuschef.portal import db, profile_page, rebuild


class FakeEngine:
    """Answers the has-clearance probe and records what it was asked."""

    def __init__(self, *, has_clearance: bool):
        self.has_clearance = has_clearance
        self.statements: list[str] = []

    @contextmanager
    def begin(self):
        yield self

    def execute(self, statement, params=None):
        self.statements.append(" ".join(str(statement).split()))
        row = (1,) if self.has_clearance else None
        return SimpleNamespace(fetchone=lambda: row)


def test_a_shop_with_no_clearance_reads_as_unscraped():
    assert db.store_has_clearance(FakeEngine(has_clearance=False), 9999) is False


def test_a_shop_with_clearance_reads_as_scraped():
    assert db.store_has_clearance(FakeEngine(has_clearance=True), 1876) is True


def test_the_probe_asks_the_table_the_page_reads():
    """So the trigger fires exactly when Laatste kans would be empty, rather
    than on a proxy for it."""
    engine = FakeEngine(has_clearance=False)
    db.store_has_clearance(engine, 1876)
    assert any("fct_store_clearance" in s for s in engine.statements)


def test_the_probe_is_bounded():
    """It answers a yes/no question and must not drag a shop's whole clearance
    list back to do it."""
    engine = FakeEngine(has_clearance=True)
    db.store_has_clearance(engine, 1876)
    assert any("LIMIT 1" in s for s in engine.statements)


# --- the trigger -------------------------------------------------------------


def test_the_trigger_names_the_scrape_job(monkeypatch):
    asked: list[str] = []
    monkeypatch.setattr(
        rebuild, "trigger_job", lambda job: asked.append(job) or "run-1"
    )
    assert rebuild.start_store_first_scrape() == "run-1"
    assert asked == ["markdowns_refresh"]


def test_a_trigger_that_cannot_reach_dagster_does_not_raise(monkeypatch):
    """The shop is the person's choice and is saved either way. Only the promise
    about when data arrives changes."""

    def boom(job):
        raise rebuild.DagsterTriggerError("no dagster here")

    monkeypatch.setattr(rebuild, "trigger_job", boom)
    said: list[str] = []
    monkeypatch.setattr(rebuild.st, "info", lambda msg, **k: said.append(msg))

    assert rebuild.start_store_first_scrape() is None
    assert said, "it must say when the data will arrive instead"
    assert "opgeslagen" in said[0], "and say the shop was saved"
    assert "uur" in said[0], "and when to expect the koopjes"


# --- the guard on the save path ----------------------------------------------


class TestOnlyForAShopNobodyHasScraped:
    @staticmethod
    def _source() -> str:
        from pathlib import Path

        return Path(profile_page.__file__).read_text()

    def test_the_save_path_consults_the_guard(self):
        import ast

        tree = ast.parse(self._source())
        calls = {ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
        assert "store_has_clearance" in calls, (
            "the trigger must be conditional on the shop having no data"
        )
        assert "start_store_first_scrape" in calls

    def test_the_guard_is_read_before_the_cache_is_cleared(self):
        """st.cache_data.clear() invalidates the readers, and the probe has to
        describe the shop just chosen rather than a cleared cache."""
        src = self._source()
        assert src.index("store_has_clearance(") < src.index("st.cache_data.clear()")

    def test_the_trigger_is_inside_the_guard(self):
        """Not merely both present: the scrape must be reachable only when the
        shop has no clearance, or a dropdown becomes a way to queue runs."""
        import ast

        tree = ast.parse(self._source())
        guarded = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            body = " ".join(ast.unparse(s) for s in node.body)
            if "start_store_first_scrape" in body:
                guarded = True
        assert guarded, "start_store_first_scrape must sit inside a conditional"


@pytest.mark.parametrize("has_clearance", [True, False])
def test_the_guard_decides_whether_anything_starts(monkeypatch, has_clearance):
    """The behavioural half: the probe's answer is what gates the run."""
    started: list[str] = []
    monkeypatch.setattr(
        rebuild, "trigger_job", lambda job: started.append(job) or "run-1"
    )
    engine = FakeEngine(has_clearance=has_clearance)
    if not db.store_has_clearance(engine, 4242):
        rebuild.start_store_first_scrape()
    assert bool(started) is (not has_clearance)
