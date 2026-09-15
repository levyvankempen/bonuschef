"""Tests for portal database helpers using a recording fake engine."""

from contextlib import contextmanager

from bonuschef.portal import db


class FakeResult:
    def __init__(self, rows=(), scalar=None):
        self._rows = list(rows)
        self._scalar = scalar

    def scalar(self):
        return self._scalar

    def __iter__(self):
        return iter(self._rows)


class FakeEngine:
    def __init__(self, *results):
        self.results = list(results)
        self.calls: list[tuple[str, dict | None]] = []

    @contextmanager
    def begin(self):
        yield self

    def execute(self, statement, params=None):
        self.calls.append((" ".join(str(statement).split()), params))
        return self.results.pop(0) if self.results else FakeResult()


def test_schema_defaults_and_env(monkeypatch):
    monkeypatch.delenv("TARGET_SCHEMA", raising=False)
    assert db._get_schema() == "public_marts"
    monkeypatch.setenv("TARGET_SCHEMA", "custom")
    assert db._get_schema() == "custom"


def test_next_recipe_id_increments_max():
    engine = FakeEngine(FakeResult(scalar=7))
    assert db.next_recipe_id(engine) == 8
    assert "MAX(recipe_id)" in engine.calls[0][0]


def test_existing_recipe_names_are_stripped():
    engine = FakeEngine(FakeResult(rows=[(" Pasta ",), ("Soep",)]))
    assert db.existing_recipe_names(engine) == {"Pasta", "Soep"}


def test_insert_recipe_binds_parameters():
    engine = FakeEngine()
    db.insert_recipe(engine, 3, "Pasta", 4)
    sql, params = engine.calls[0]
    assert sql.startswith("INSERT INTO public.recipes")
    assert params == {"id": 3, "name": "Pasta", "servings": 4}


def test_insert_ingredients_one_row_per_item():
    engine = FakeEngine()
    db.insert_ingredients(engine, 3, [("Melk", "1/melk", 2), ("Kaas", "2/kaas", 1)])
    assert len(engine.calls) == 2
    assert engine.calls[0][1] == {
        "rid": 3,
        "pname": "Melk",
        "plink": "1/melk",
        "qty": 2,
    }
    assert "valid_from" in engine.calls[0][0]


def test_upsert_product_image_uses_on_conflict():
    engine = FakeEngine()
    db.upsert_product_image(engine, "1/melk", "https://img")
    sql, params = engine.calls[0]
    assert "ON CONFLICT (product_link)" in sql
    assert params == {"product_link": "1/melk", "image_url": "https://img"}


def test_ensure_tables_are_idempotent_ddl():
    engine = FakeEngine()
    db.ensure_recipe_tables(engine)
    db.ensure_product_images_table(engine)
    assert len(engine.calls) == 3
    assert all(sql.startswith("CREATE TABLE IF NOT EXISTS") for sql, _ in engine.calls)


class TestFreshnessIsJudgedOnTheAnswer:
    """A successful load followed by a failed rebuild left the source fresh and
    every figure frozen. The banner's question is "how old is this answer", and
    the answer is what dbt built."""

    def test_the_query_consults_both_clocks(self):
        import inspect

        from bonuschef.portal.db import read_bonus_feed_loaded_at

        sql = inspect.getsource(read_bonus_feed_loaded_at)
        assert "LEAST(" in sql, "one clock cannot report the other stopping"
        assert "ah__bonus_products" in sql, "the feed's load time"
        assert "fct_bonus_price_comparison" in sql, "the mart's build time"
        assert "built_at" in sql

    def test_the_mart_records_when_it_was_built(self):
        from pathlib import Path

        model = (
            Path(__file__).resolve().parents[2]
            / "src/bonuschef/sql/models/marts/inventory/fct_bonus_price_comparison.sql"
        )
        assert "built_at" in model.read_text(), (
            "without it the portal has no way to know the rebuild stopped"
        )
