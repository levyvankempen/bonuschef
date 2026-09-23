"""Deleting a recipe must delete it.

`seed_default_recipes()` ran as an on-run-start hook and inserted a default
recipe whenever `public.recipes` was empty. The intent was to give a fresh
environment something to look at. The effect, once the environment stopped
being fresh, was that deleting every hand-entered recipe silently brought one
back on the next dbt run - and dbt runs hourly.

Observed on 2026-09-21: two hand-entered recipes were deleted, the table went
empty, `daily_refresh` ran, and recipe 1 reappeared with all twelve of its
ingredient lines. The second recipe stayed deleted, because by then the table
was no longer empty - which is a strange enough symptom to lose an afternoon
to.

The seeded rows were also stale: product links with `valid_to` dates from
February 2025, carrying a history of Iglo Kibbeling renames. A fresh
environment was being handed a year-old shopping list.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SQL = ROOT / "src" / "bonuschef" / "sql"
PROJECT = SQL / "dbt_project.yml"


def test_no_hook_writes_recipes():
    """An on-run-start hook that writes user data runs on every dbt
    invocation, which here is hourly. Schema statements are one thing; rows a
    person can delete are another."""
    body = PROJECT.read_text()
    start = body.index("on-run-start")
    hooks = body[start : body.index("vars:", start)]
    assert "INSERT INTO public.recipes" not in hooks, hooks
    assert "seed_default_recipes" not in hooks, hooks


def test_the_seeding_macro_is_gone():
    assert not (SQL / "macros" / "seed_default_recipes.sql").exists()


def test_nothing_still_calls_it():
    """A dangling call would fail every dbt run, which is a louder failure
    than the one being fixed but still a failure."""
    for path in SQL.rglob("*"):
        if (
            not path.is_file()
            or "target" in path.parts
            or path.suffix
            not in {
                ".sql",
                ".yml",
            }
        ):
            continue
        assert "seed_default_recipes" not in path.read_text(), path
